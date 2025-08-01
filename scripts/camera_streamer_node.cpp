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
    
    // UDP members
    boost::asio::io_service io_service_;
    udp::socket udp_socket_;
    udp::endpoint remote_endpoint_;
    
    // Configuration
    std::string camera_name_;
    std::string image_topic_;
    std::string target_ip_;
    int target_port_;
    int fps_;
    int width_;
    int height_;
    int jpeg_quality_;
    
    // Port management
    ros::Publisher port_pub_;
    ros::Subscriber ip_sub_;
    ros::Subscriber ports_sub_;
    std::string port_registry_;
    bool port_registered_;
    bool has_target_ip_;
    
    // Constants
    static const int MTU = 1400;
    uint32_t frame_id_;
    
public:
    CameraStreamerNode() : 
        it_(nh_),
        udp_socket_(io_service_),
        target_port_(-1),
        port_registered_(false),
        has_target_ip_(false),
        frame_id_(0)
    {
	srand(time(NULL));
        // Load parameters
        ros::NodeHandle private_nh("~");
        private_nh.param<std::string>("camera_name", camera_name_, "default_camera");
        private_nh.param<std::string>("image_topic", image_topic_, camera_name_ + "/color/image_raw");
        private_nh.param<int>("fps", fps_, 30);
        private_nh.param<int>("width", width_, 640);
        private_nh.param<int>("height", height_, 480);
        private_nh.param<int>("jpeg_quality", jpeg_quality_, 75);
        
        // Initialize UDP socket
        udp_socket_.open(udp::v4());
        
        // Setup ROS communication
        port_pub_ = nh_.advertise<std_msgs::String>("udpcam/ports", 1, true);
        ip_sub_ = nh_.subscribe("unity/ip", 1, &CameraStreamerNode::ipCallback, this);
        ports_sub_ = nh_.subscribe("udpcam/ports", 1, &CameraStreamerNode::portsCallback, this);
        
        // Subscribe to image topic with camera-specific name
        image_sub_ = it_.subscribe(image_topic_, 1, &CameraStreamerNode::imageCallback, this);
        ROS_INFO("Subscribed to image topic: %s", image_topic_.c_str());
        
        // Attempt to register port
        registerPort();
        
        ROS_INFO("CameraStreamerNode initialized for camera: %s", camera_name_.c_str());
    }
    
    ~CameraStreamerNode()
    {
        udp_socket_.close();
    }
    
    void ipCallback(const std_msgs::String::ConstPtr& msg)
    {
        target_ip_ = msg->data;
        has_target_ip_ = true;
        ROS_INFO("Received target IP: %s", target_ip_.c_str());
    }
    
    void portsCallback(const std_msgs::String::ConstPtr& msg)
    {
        port_registry_ = msg->data;
        
        // If we haven't registered our port yet, try now
        if (!port_registered_)
        {
            registerPort();
        }
    }
    
    void registerPort()
    {
        if (port_registry_.empty())
        {
            // No existing registry, create new one
            target_port_ = randomPort(5000, 6000);
            std_msgs::String msg;
            msg.data = camera_name_ + ":" + std::to_string(target_port_);
            port_pub_.publish(msg);
            port_registered_ = true;
            ROS_INFO("Registered new port: %d", target_port_);
        }
        else
        {
            // Parse existing registry
            std::vector<std::string> entries;
            boost::split(entries, port_registry_, boost::is_any_of("&"));
            
            // Check if our camera is already registered
            for (const auto& entry : entries)
            {
                std::vector<std::string> parts;
                boost::split(parts, entry, boost::is_any_of(":"));
                if (parts.size() == 2 && parts[0] == camera_name_)
                {
                    target_port_ = std::stoi(parts[1]);
                    port_registered_ = true;
                    ROS_INFO("Found existing port registration: %d", target_port_);
                    return;
                }
            }
            
            // Find an available port
            std::set<int> used_ports;
            for (const auto& entry : entries)
            {
                std::vector<std::string> parts;
                boost::split(parts, entry, boost::is_any_of(":"));
                if (parts.size() == 2)
                {
                    used_ports.insert(std::stoi(parts[1]));
                }
            }
            
            // Assign new port
            while (target_port_ == -1)
            {
                int candidate = randomPort(5000, 6000);
                if (used_ports.find(candidate) == used_ports.end())
                {
                    target_port_ = candidate;
                    std_msgs::String msg;
                    msg.data = port_registry_ + "&" + camera_name_ + ":" + std::to_string(target_port_);
                    port_pub_.publish(msg);
                    port_registered_ = true;
                    ROS_INFO("Registered new port in existing registry: %d", target_port_);
                }
            }
        }
    }
    
    int randomPort(int min, int max)
    {
        return min + (rand() % (max - min + 1));
    }
    
    void imageCallback(const sensor_msgs::ImageConstPtr& msg)
    {
        if (!has_target_ip_ || target_port_ == -1)
        {
            ROS_WARN_THROTTLE(5, "Waiting for target IP and port assignment...");
            return;
        }
        
        try
        {
            // Convert ROS image to OpenCV
            cv_bridge::CvImagePtr cv_ptr = cv_bridge::toCvCopy(msg, sensor_msgs::image_encodings::BGR8);
            
            // Resize if needed
            cv::Mat frame;
            if (cv_ptr->image.cols != width_ || cv_ptr->image.rows != height_)
            {
                cv::resize(cv_ptr->image, frame, cv::Size(width_, height_));
            }
            else
            {
                frame = cv_ptr->image;
            }
            
            // Encode to JPEG
            std::vector<int> params;
            params.push_back(cv::IMWRITE_JPEG_QUALITY);
            params.push_back(jpeg_quality_);
            std::vector<uchar> jpeg_buffer;
            cv::imencode(".jpg", frame, jpeg_buffer, params);
            
            // Send via UDP
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
        int max_payload = MTU - 8; // 8 byte header
        int total_fragments = (frame_data.size() + max_payload - 1) / max_payload;
        
        for (ushort i = 0; i < total_fragments; i++)
        {
            int offset = i * max_payload;
            int size = std::min(max_payload, static_cast<int>(frame_data.size()) - offset);
            
            // Create packet buffer
            std::vector<uchar> packet(8 + size);
            
            // Write header (frameId, totalFragments, fragmentIndex)
            uint32_t net_frame_id = htonl(frame_id_);
            uint16_t net_total_frags = htons(total_fragments);
            uint16_t net_frag_idx = htons(i);
            
            memcpy(&packet[0], &net_frame_id, 4);
            memcpy(&packet[4], &net_total_frags, 2);
            memcpy(&packet[6], &net_frag_idx, 2);
            
            // Copy payload
            memcpy(&packet[8], &frame_data[offset], size);
            
            // Send packet
            try
            {
                remote_endpoint_ = udp::endpoint(boost::asio::ip::address::from_string(target_ip_), target_port_);
                udp_socket_.send_to(boost::asio::buffer(packet), remote_endpoint_);
            }
            catch (std::exception& e)
            {
                ROS_ERROR("UDP send error: %s", e.what());
            }
        }
    }
};





std::string extractCameraName(int argc, char** argv, const std::string& default_name = "default_camera")
{
    for (int i = 1; i < argc; ++i)
    {
        std::string arg(argv[i]);
        const std::string prefix = "__camera_name:=";
        if (arg.find(prefix) != std::string::npos)
        {
            return arg.substr(prefix.length());
        }
    }
    return default_name;
}

int main(int argc, char** argv)
{
    std::string camera_name = extractCameraName(argc, argv);
    std::string node_name = "camera_streamer_node_" + camera_name;

    ros::init(argc, argv, node_name);
    CameraStreamerNode node;
    ros::spin();
    return 0;
}


