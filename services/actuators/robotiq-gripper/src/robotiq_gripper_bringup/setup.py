from setuptools import find_packages, setup
import glob

package_name = "robotiq_gripper_bringup"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/config", glob.glob("config/*.yaml")),
        ("share/" + package_name + "/launch", glob.glob("launch/*.launch.py")),
        ("share/" + package_name + "/urdf", glob.glob("urdf/*.urdf.xacro")),
    ],
    include_package_data=True,
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Franka Robotics GmbH",
    maintainer_email="support@franka.de",
    description="Bringup for Robotiq 2F grippers on the official robotiq/ros driver.",
    license="Apache 2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "robotiq_gripper_client = robotiq_gripper_bringup.robotiq_gripper_client:main",
        ],
    },
)
