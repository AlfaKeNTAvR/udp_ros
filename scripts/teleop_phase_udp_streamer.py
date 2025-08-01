#!/usr/bin/env python
"""Implements UDP for ROS1-Unity teleop phase streaming.

Author(s):
    1. Dimitri Saliba (dimitriasaliba@gmail.com), ECE, Worcester Polytechnic
       Institute (WPI), 2022.
    2. Nikita Boguslavskii (bognik3@gmail.com), Human-Inspired Robotics (HiRo)
       lab, Worcester Polytechnic Institute (WPI), 2023.
    3. Modified by Filippo Marcantoni (filippo.marcantoni@gmail.com), (WPI), 2025.

Description: 
    Streams `teleop_phase_topic` messages via UDP to the Windows computer running Unity and the multicamera system.

"""

# Standart libraries:
import rospy
import numpy as np
from std_msgs.msg import (
    String,
    Float32,
)
from geometry_msgs.msg import (Twist)
from sensor_msgs.msg import (JointState)

from socket import (
    socket,
    AF_INET,
    SOCK_DGRAM,
)


class TeleopPhaseUDPStreamer:
    """
    
    """

    def __init__(self, node_name, topic, udp_ip, udp_port):
        """Initialize TeleopPhaseUDPStreamer node."""

        # ROS parameters
        self._TOPIC = topic
        self.__UDP_IP = udp_ip
        self.__UDP_PORT = udp_port

        # Create UDP socket
        self.__UDP_SOCKET = socket(
            AF_INET,
            SOCK_DGRAM,
        )

        # ROS Node:
        self.NODE_NAME = node_name

        # Subscribe to the teleop phase topic
        rospy.Subscriber(
            "/chest_logger/current_velocity",
            Float32,
            self.__message_chest_callback,
        )

        rospy.Subscriber(
            "/base_controller/command",
            Twist,
            self.__message_nav_callback,
        )

        rospy.Subscriber(
            "/right_arm/base_feedback/joint_state",
            JointState,
            self.__message_right_arm_callback,
        )
        rospy.Subscriber(
            "/left_arm/base_feedback/joint_state",
            JointState,
            self.__message_left_arm_callback,
        )

        #rospy.Subscriber(self._TOPIC, String, self.__message_callback)

        rospy.loginfo(
            f"{self.NODE_NAME} initialized.\n"
            f"Streaming topic: {self._TOPIC}\n"
            f"Sending to UDP {self.__UDP_IP}:{self.__UDP_PORT}"
        )

    # Topic callbacks:
    def __message_chest_callback(self, message):
        """Callback for the teleop phase topic messages."""
        # rospy.loginfo(f"Received message from chest: {message.data}")
        if message.data > 0.1:
            phase = "CHEST MANIPULATION"
            data = phase.encode("utf-8")
            self.__UDP_SOCKET.sendto(data, (self.__UDP_IP, self.__UDP_PORT))
            rospy.loginfo(f"Sent message: {phase}")

    def __message_nav_callback(self, message):
        """Callback for the teleop phase topic messages."""
        # rospy.loginfo(
        #     f"Received message from nav: {message.linear} & {message.angular}."
        # )
        if message.linear.x > 0.1 or message.angular.z > 0.1:
            phase = "NAVIGATION"
            data = phase.encode("utf-8")
            self.__UDP_SOCKET.sendto(data, (self.__UDP_IP, self.__UDP_PORT))
            rospy.loginfo(f"Sent message: {phase}")

    def __message_left_arm_callback(self, message):
        """Callback for the teleop phase topic messages."""
        # rospy.loginfo(f"Received message from left arm: {message.velocity}")
        for i, v in enumerate(message.velocity):
            if v > 0.1:
                print(f"Index {i} has a nonzero value: {v}")
                phase = "LEFT ARM MANIPULATION"
                data = phase.encode("utf-8")
                self.__UDP_SOCKET.sendto(data, (self.__UDP_IP, self.__UDP_PORT))
                rospy.loginfo(f"Sent message: {phase}")
                break

    def __message_right_arm_callback(self, message):
        """Callback for the teleop phase topic messages."""
        # rospy.loginfo(f"Received message from right arm: {message.velocity}")
        for i, v in enumerate(message.velocity):
            if v > 0.1:
                print(f"Index {i} has a nonzero value: {v}")
                phase = "RIGHT ARM MANIPULATION"
                data = phase.encode("utf-8")
                self.__UDP_SOCKET.sendto(data, (self.__UDP_IP, self.__UDP_PORT))
                rospy.loginfo(f"Sent message: {phase}")
                break

    def node_shutdown(self):
        """Cleanup on shutdown."""
        rospy.loginfo(f"{self.NODE_NAME} shutting down...")
        self.__UDP_SOCKET.close()

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
    rospy.init_node("udp_teleop_streamer", anonymous=True)

    # Load parameters (modify as needed)
    # udp_ip = "192.168.1.100"  # Replace with Windows machine IP
    # udp_port = 5005           # Replace with desired UDP port
    # topic_name = "teleop_phase_topic"

    rospy.loginfo('\n\n\n\n\n')  # Add whitespaces to separate logs.

    # ROS launch file parameters:
    node_name = rospy.get_name()

    node_frequency = rospy.get_param(
        param_name=f'{rospy.get_name()}/node_frequency',
        default=100,
    )
    topic = rospy.get_param(
        param_name=f'{rospy.get_name()}/teleop_phase_topic',
        default='/rteleop_phase_topic',
    )
    udp_ip = rospy.get_param(
        param_name=f'{rospy.get_name()}/udp_ip',
        default='192.168.0.100',
    )
    udp_port = rospy.get_param(
        param_name=f'{rospy.get_name()}/udp_port',
        default=8083,
    )

    streamer = TeleopPhaseUDPStreamer(
        "udp_teleop_streamer", topic, udp_ip, udp_port
    )

    try:
        rospy.spin()
    except KeyboardInterrupt:
        streamer.node_shutdown()


if __name__ == '__main__':
    main()
