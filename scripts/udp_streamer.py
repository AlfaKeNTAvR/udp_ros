#!/usr/bin/env python
"""Implements UDP for ROS1-Unity image streaming.

Author(s):
    1. Dimitri Saliba (dimitriasaliba@gmail.com), ECE, Worcester Polytechnic
       Institute (WPI), 2022.
    2. Nikita Boguslavskii (bognik3@gmail.com), Human-Inspired Robotics (HiRo)
       lab, Worcester Polytechnic Institute (WPI), 2023.

TODO: 
    1. Add detailed description.
    2. 'Bluish' image issue.

"""

# # Standart libraries:
import rospy
import numpy as np
from math import (ceil)
from cv2 import (
    IMWRITE_JPEG_QUALITY,
    imshow,
    waitKey,
    imencode,
    # cvtColor,
    # COLOR_BGR2RGB,
)
from cv_bridge import (
    CvBridge,
    CvBridgeError,
)
from socket import (
    socket,
    AF_INET,
    SOCK_DGRAM,
)

# # Third party libraries:

# # Standart messages and services:
from std_msgs.msg import (Bool)
from sensor_msgs.msg import (Image)

# # Third party messages and services:


class UDPStreamer:
    """
    
    """

    def __init__(
        self,
        node_name,
        image_topic,
        udp_ip,
        udp_port,
        chunk_size,
        fps_rate,
        jpg_quality,
        enable_imshow,
    ):
        """
        
        """

        # # Private constants:
        self.__IMAGE_TOPIC = image_topic
        self.__UDP_IP = udp_ip
        self.__UDP_PORT = udp_port
        self.__CHUNK_SIZE = chunk_size
        self.__FPS_RATE = fps_rate
        self.__ENABLE_IMSHOW = enable_imshow

        self.__JPG_ENCODE_PARAMETERS = [
            int(IMWRITE_JPEG_QUALITY),
            jpg_quality,
        ]
        self.__BRIDGE = CvBridge()
        self.__UDP_SOCKET = socket(
            AF_INET,
            SOCK_DGRAM,
        )

        # # Public constants:
        self.NODE_NAME = node_name

        # # Private variables:
        self.__cv_image = None
        self.__frame_number = 0

        # # Public variables:

        # # Initialization and dependency status topics:
        self.__is_initialized = False
        self.__dependency_initialized = False

        self.__node_is_initialized = rospy.Publisher(
            f'{self.NODE_NAME}/is_initialized',
            Bool,
            queue_size=1,
        )

        # NOTE: Specify dependency initial False initial status.
        self.__dependency_status = {
            'image_topic': False,
        }

        # NOTE: Specify dependency is_initialized topic (or any other topic,
        # which will be available when the dependency node is running properly).
        self.__dependency_status_topics = {}

        self.__dependency_status_topics['image_topic'] = (
            rospy.Subscriber(
                f'{self.__IMAGE_TOPIC}',
                Image,
                self.__camera_callback,
            )
        )

        # # Service provider:

        # # Service subscriber:

        # # Topic publisher:

        # # Topic subscriber:
        rospy.Subscriber(
            f'{self.__IMAGE_TOPIC}',
            Image,
            self.__camera_callback,
        )

        # # Timers:
        rospy.Timer(
            rospy.Duration(1.0 / self.__FPS_RATE),
            self.__udp_stream_timer,
        )

        # # Node parameters:
        rospy.loginfo(
            f'{self.NODE_NAME}:'
            '\nNode parameters:'
            f'\n- image_topic: {self.__IMAGE_TOPIC}'
            f'\n- udp_ip: {self.__UDP_IP}'
            f'\n- udp_port: {self.__UDP_PORT}'
            f'\n- chunk_size: {self.__CHUNK_SIZE}'
            f'\n- fps_rate: {self.__FPS_RATE}'
            f'\n- enable_imshow: {self.__ENABLE_IMSHOW}'
            '\n'
        )

    # # Dependency status callbacks:
    # NOTE: each dependency topic should have a callback function, which will
    # set __dependency_status variable.

    # # Service handlers:

    # # Topic callbacks:
    def __camera_callback(self, message):
        """
        
        """

        try:
            self.__cv_image = self.__BRIDGE.imgmsg_to_cv2(
                message,
                'bgr8',
            )
            # # TODO: Uncomment if the image appears bluish:
            # self.__cv_image = cvtColor(
            #     self.__cv_image,
            #     COLOR_BGR2RGB,
            # )

            if not self.__is_initialized:
                self.__dependency_status['image_topic'] = True

        except CvBridgeError as e:
            print(e)

    # Timer callbacks:
    def __udp_stream_timer(self, event):
        """Calls udp_stream on each timer callback with FPS frequency.

        """

        self.__udp_stream()

    # # Private methods:
    def __check_initialization(self):
        """Monitors required criteria and sets is_initialized variable.

        Monitors nodes' dependency status by checking if dependency's
        is_initialized topic has at most one publisher (this ensures that
        dependency node is alive and does not have any duplicates) and that it
        publishes True. If dependency's status was True, but get_num_connections
        is not equal to 1, this means that the connection is lost and emergency
        actions should be performed.

        Once all dependencies are initialized and additional criteria met, the
        nodes' is_initialized status changes to True. This status can change to
        False any time to False if some criteria are no longer met.
        
        """

        self.__dependency_initialized = True

        for key in self.__dependency_status:
            if self.__dependency_status_topics[key].get_num_connections() != 1:
                if self.__dependency_status[key]:
                    rospy.logerr(
                        (f'{self.NODE_NAME}: '
                         f'lost connection to {key}!')
                    )

                    # # Emergency actions on lost connection:
                    # NOTE (optionally): Add code, which needs to be executed if
                    # connection to any of dependencies was lost.

                self.__dependency_status[key] = False

            if not self.__dependency_status[key]:
                self.__dependency_initialized = False

        if not self.__dependency_initialized:
            waiting_for = ''
            for key in self.__dependency_status:
                if not self.__dependency_status[key]:
                    waiting_for += f'\n- waiting for {key} node...'

            rospy.logwarn_throttle(
                15,
                (
                    f'{self.NODE_NAME}:'
                    f'{waiting_for}'
                    # f'\nMake sure those dependencies are running properly!'
                ),
            )

        # NOTE (optionally): Add more initialization criterea if needed.
        if (self.__dependency_initialized):
            if not self.__is_initialized:
                rospy.loginfo(f'\033[92m{self.NODE_NAME}: ready.\033[0m',)

                self.__is_initialized = True

        else:
            if self.__is_initialized:
                # NOTE (optionally): Add code, which needs to be executed if the
                # nodes's status changes from True to False.
                pass

            self.__is_initialized = False

        self.__node_is_initialized.publish(self.__is_initialized)

    def __udp_stream(self):
        """
        
        """

        if self.__cv_image is None:
            return

        # Optionally show the frame.
        if self.__ENABLE_IMSHOW:
            imshow(
                'self.__cv_image',
                self.__cv_image,
            )

            if waitKey(1) & 0xFF == ord('q'):
                pass

        # Encode image as jpg and calculate chunks.
        data_string = (
            np.array(
                imencode(
                    '.jpg',
                    self.__cv_image,
                    self.__JPG_ENCODE_PARAMETERS,
                )[1]
            ).tobytes()
        )
        frame_size = len(data_string)

        current_index = 0
        current_chunk = 0

        max_chunks = ceil(frame_size / self.__CHUNK_SIZE)

        while current_index < frame_size:
            payload_size = self.__CHUNK_SIZE

            if current_index + self.__CHUNK_SIZE > frame_size:
                payload_size = frame_size - current_index

            payload = data_string[current_index:current_index + payload_size]
            header = (
                f'{self.__frame_number}_'
                f'{current_chunk}_'
                f'{max_chunks}_'
                f'{current_index}_'
                f'{payload_size}_'
                f'{frame_size}'
            )

            packet = bytes(header, 'utf-8') + bytes(1) + payload
            self.__UDP_SOCKET.sendto(
                packet,
                (
                    self.__UDP_IP,
                    self.__UDP_PORT,
                ),
            )

            current_chunk = current_chunk + 1
            current_index = current_index + self.__CHUNK_SIZE

        rospy.logdebug(
            f'Frame: {self.__frame_number}'
            f'Chunk Count: {max_chunks}'
        )

        self.__frame_number = self.__frame_number + 1

    # # Public methods:
    def main_loop(self):
        """
        
        """

        self.__check_initialization()

        if not self.__is_initialized:
            return

        # NOTE: Add code (function calls), which has to be executed once the
        # node was successfully initialized.

    def node_shutdown(self):
        """
        
        """

        rospy.loginfo_once(f'{self.NODE_NAME}: node is shutting down...',)

        # NOTE: Add code, which needs to be executed on nodes' shutdown here.
        # Publishing to topics is not guaranteed, use service calls or
        # set parameters instead.

        rospy.loginfo_once(f'{self.NODE_NAME}: node has shut down.',)


def main():
    """
    
    """

    # # Default node initialization.
    # This name is replaced when a launch file is used.
    rospy.init_node(
        'udp_streamer',
        log_level=rospy.INFO,  # rospy.DEBUG to view debug messages.
    )

    rospy.loginfo('\n\n\n\n\n')  # Add whitespaces to separate logs.

    # # ROS launch file parameters:
    node_name = rospy.get_name()

    node_frequency = rospy.get_param(
        param_name=f'{rospy.get_name()}/node_frequency',
        default=100,
    )
    image_topic = rospy.get_param(
        param_name=f'{rospy.get_name()}/image_topic',
        default='/camera/color/image_raw',
    )
    udp_ip = rospy.get_param(
        param_name=f'{rospy.get_name()}/udp_ip',
        default='192.168.0.100',
    )
    udp_port = rospy.get_param(
        param_name=f'{rospy.get_name()}/udp_port',
        default=8080,
    )
    chunk_size = rospy.get_param(
        param_name=f'{node_name}/chunk_size',
        default=32000,
    )
    fps_rate = rospy.get_param(
        param_name=f'{node_name}/fps_rate',
        default=30,
    )
    jpg_quality = rospy.get_param(
        param_name=f'{node_name}/jpg_quality',
        default=80,
    )
    enable_imshow = rospy.get_param(
        param_name=f'{node_name}/enable_imshow',
        default=False,
    )

    class_instance = UDPStreamer(
        node_name=node_name,
        image_topic=image_topic,
        udp_ip=udp_ip,
        udp_port=udp_port,
        chunk_size=chunk_size,
        fps_rate=fps_rate,
        jpg_quality=jpg_quality,
        enable_imshow=enable_imshow,
    )

    rospy.on_shutdown(class_instance.node_shutdown)
    node_rate = rospy.Rate(node_frequency)

    while not rospy.is_shutdown():
        class_instance.main_loop()
        node_rate.sleep()


if __name__ == '__main__':
    main()
