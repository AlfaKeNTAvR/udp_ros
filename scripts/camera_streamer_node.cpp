#include <ros/ros.h>
#include <image_transport/image_transport.h>
#include <cv_bridge/cv_bridge.h>
#include <sensor_msgs/image_encodings.h>
#include <std_msgs/String.h>
#include <opencv2/imgproc/imgproc.hpp>
#include <opencv2/highgui/highgui.hpp>
#include <boost/asio.hpp>
#include <boost/algorithm/string.hpp>
#include <vector>
#include <string>
#include <set>
#include <arpa/inet.h>

using boost::asio::ip::udp;

class CameraStreamerNode
{
private:
    ros::NodeHandle nh_;
    image_transport::ImageTransport it_;
    image_transport::Subscriber image_sub_;

    boost::asio::io_service io_service_;
    udp::socket udp_socket_;
    udp::endpoint remote_endpoint_;

    std::string camera_name_;
    std::string image_topic_;
    std::string target_ip_;
    int target_port_;
    int fps_;
    int width_;
    int height_;
    int jpeg_quality_;

    ros::Publisher port_pub_;
    ros::Subscriber ip_sub_;
    ros::Subscriber ports_sub_;
    std::string port_registry_;
    bool port_registered_;
    bool has_target_ip_;

    static const int MTU = 1400;
    uint32_t frame_id_;

public:

    CameraStreamerNode()
        : it_(nh_),
          udp_socket_(io_service_),
          target_port_(-1),
          port_registered_(false),
          has_target_ip_(false),
          frame_id_(0)
    {
        // Load parameters
        ros::NodeHandle private_nh("~");
        private_nh.param<std::string>("camera_name", camera_name_, "default_camera");
        private_nh.param<std::string>("image_topic", image_topic_, camera_name_ + "/color/image_raw");

        private_nh.param<int>("fps", fps_, 30);
        private_nh.param<int>("width", width_, 640);
        private_nh.param<int>("height", height_, 480);
        private_nh.param<int>("jpeg_quality", jpeg_quality_, 75);

        // --- NEW: Seed RNG by camera name (prevents both nodes picking same ports) ---
        unsigned long seed = 5381;
        for (char c : camera_name_) seed = ((seed << 5) + seed) + c;
        srand(seed ^ time(NULL));

        udp_socket_.open(udp::v4());

        port_pub_  = nh_.advertise<std_msgs::String>("udpcam/ports", 10, true);
        ip_sub_    = nh_.subscribe("unity/ip",   10, &CameraStreamerNode::ipCallback,   this);
        ports_sub_ = nh_.subscribe("udpcam/ports", 10, &CameraStreamerNode::portsCallback, this);

        image_sub_ = it_.subscribe(image_topic_, 1, &CameraStreamerNode::imageCallback, this);

        ROS_INFO("[%s] Subscribed to: %s", camera_name_.c_str(), image_topic_.c_str());

        // Try to register port immediately
        tryRegisterPort();
    }

    // -----------------------------
    // PORT REGISTRY FIXES START HERE
    // -----------------------------

    void portsCallback(const std_msgs::String::ConstPtr& msg)
    {
        port_registry_ = msg->data;
        tryRegisterPort();   // always retry if not registered
    }

    void tryRegisterPort()
    {
        if (port_registered_) return;

        std::vector<std::string> entries;
        if (!port_registry_.empty())
            boost::split(entries, port_registry_, boost::is_any_of("&"));

        // Check if already present
        for (auto &e : entries)
        {
            std::vector<std::string> parts;
            boost::split(parts, e, boost::is_any_of(":"));

            if (parts.size() == 2 && parts[0] == camera_name_)
            {
                target_port_ = std::stoi(parts[1]);
                port_registered_ = true;
                ROS_INFO("[%s] Using existing port %d",
                        camera_name_.c_str(), target_port_);
                return;
            }
        }

        // Collect used ports so far
        std::set<int> used;
        for (auto &e : entries)
        {
            std::vector<std::string> parts;
            boost::split(parts, e, boost::is_any_of(":"));
            if (parts.size() == 2)
                used.insert(std::stoi(parts[1]));
        }

        // Pick available port
        int new_port;
        while (true)
        {
            new_port = randomPort(5000, 6000);
            if (!used.count(new_port)) break;
        }

        target_port_ = new_port;

        // Update registry
        std::string new_entry = camera_name_ + ":" + std::to_string(target_port_);
        std::string new_registry = port_registry_.empty()
            ? new_entry
            : port_registry_ + "&" + new_entry;

        port_registry_ = new_registry;

        std_msgs::String msg;
        msg.data = port_registry_;
        port_pub_.publish(msg);

        port_registered_ = true;

        ROS_INFO("[%s] Registered port %d", camera_name_.c_str(), target_port_);
    }

    int randomPort(int min, int max)
    {
        return min + (rand() % (max - min + 1));
    }

    // -----------------------------
    // PORT FIXES END
    // -----------------------------


    // Image + UDP parts UNCHANGED ---------------------------------

    void ipCallback(const std_msgs::String::ConstPtr& msg)
    {
        target_ip_ = msg->data;
        has_target_ip_ = true;
        ROS_INFO("[%s] Target IP set to %s", camera_name_.c_str(), target_ip_.c_str());
    }

    void imageCallback(const sensor_msgs::ImageConstPtr& msg)
    {
        if (!has_target_ip_ || target_port_ == -1)
        {
            ROS_WARN_THROTTLE(5, "[%s] Waiting for IP and port...", camera_name_.c_str());
            return;
        }

        try
        {
            cv_bridge::CvImagePtr cv_ptr = cv_bridge::toCvCopy(msg, sensor_msgs::image_encodings::BGR8);

            cv::Mat frame;
            if (cv_ptr->image.cols != width_ || cv_ptr->image.rows != height_)
                cv::resize(cv_ptr->image, frame, cv::Size(width_, height_));
            else
                frame = cv_ptr->image;

            std::vector<int> params = { cv::IMWRITE_JPEG_QUALITY, jpeg_quality_ };
            std::vector<uchar> jpeg_buffer;
            cv::imencode(".jpg", frame, jpeg_buffer, params);

            sendFragmented(jpeg_buffer);
            frame_id_++;
        }
        catch (cv_bridge::Exception& e)
        {
            ROS_ERROR("cv_bridge exception: %s", e.what());
        }
    }

    void sendFragmented(const std::vector<uchar>& frame_data)
    {
        int max_payload = MTU - 8;
        int total_fragments = (frame_data.size() + max_payload - 1) / max_payload;

        for (uint16_t i = 0; i < total_fragments; i++)
        {
            int offset = i * max_payload;
            int size = std::min(max_payload, (int)frame_data.size() - offset);

            std::vector<uchar> packet(8 + size);

            uint32_t net_frame_id = htonl(frame_id_);
            uint16_t net_total_frags = htons(total_fragments);
            uint16_t net_frag_idx = htons(i);

            memcpy(&packet[0], &net_frame_id, 4);
            memcpy(&packet[4], &net_total_frags, 2);
            memcpy(&packet[6], &net_frag_idx, 2);
            memcpy(&packet[8], &frame_data[offset], size);

            try
            {
                remote_endpoint_ = udp::endpoint(
                    boost::asio::ip::address::from_string(target_ip_), target_port_);
                udp_socket_.send_to(boost::asio::buffer(packet), remote_endpoint_);
            }
            catch (...) {}
        }
    }
};


int main(int argc, char** argv)
{
    ros::init(argc, argv, "camera_streamer_node");
    CameraStreamerNode node;
    ros::spin();
    return 0;
}

