workspace {
    name "LABS"
    description "Teleoperation-based robot learning system based on Franka robots"

    model {
        user = person "Operator" "Human operator controlling the robot system and data recording workflow"

        group "LABS" {
            # External teleoperation devices
            teleopSystem = softwareSystem "Teleoperation Devices" "External control devices and their ROS interfaces" {
                tags "TeleopDevice"

                # GELLO wearable
                gelloHardware = container "GELLO Hardware" "Physical wearable device" "Haptic Device" {
                    tags "InputDevice"
                }
                gelloSoftware = container "GELLO Software" "gello_software ROS driver" "ROS 2/Python" {
                    tags "ROSDriver"
                }

                # Franka leader robots used for teleoperation
                fr3Leader = container "FR3 Leader Robot" "Single arm Franka FR3 used as leader" "Physical Robot" {
                    tags "PhysicalRobot"
                }
                fr3DuoLeader = container "FR3 Leader Duo" "Dual arm Franka FR3 leader" "Physical Robot" {
                    tags "PhysicalRobot"
                }
                fr3Teleop = container "fr3_ros2_teleop" "Leader control stack" "ROS 2" {
                    tags "ROSInterface"
                }

                # Additional custom devices
                teleopDevices = container "Custom Hardware" "Various teleoperation devices" "Hardware" {
                    tags "InputDevice"
                }
                teleopDrivers = container "Specific Drivers" "Device-specific ROS drivers" "ROS 2/Python" {
                    tags "ROSDriver"
                }
            }

            cameraSystem = softwareSystem "Camera System" "Head, wrist, and environmental cameras with their ROS drivers" {
                tags "SensorSystem"
                headCamera = container "Head Camera" "Primary vision sensor" "Camera Hardware" {
                    tags "CameraHardware"
                }
                wristCameras = container "Wrist Cameras" "Cameras mounted on wrists" "Camera Hardware" {
                    tags "CameraHardware"
                }
                bodyCamera = container "Body Camera" "Optional body camera for close-up views" "Camera Hardware" {
                    tags "CameraHardware"
                }
                cameraDrivers = container "Camera Drivers" "ROS drivers for camera feeds" "ROS 2/Python" {
                    tags "ROSDriver"
                }
            }

            dataCollectionPlatform = softwareSystem "LABS" "Microservice-driven robotics data orchestration platform" {
                tags "FrankaSWSystem"

                dataCollectionUI = container "Data Collection UI" "Dashboard for device health check monitoring, teleoperation, live camera streaming and session management" "React/Vite" {
                    tags "WebApp"
                }

                dataCollectionService = container "Data Collection Service" "FastAPI services that coordinates teleop workflow, device health, and recorder commands." "FastAPI/Python" {
                    tags "Service"

                    episodeHandlers = component "Episode & Teleop APIs" "FastAPI endpoints for auth, tasks, devices, teleop" "FastAPI" {
                        tags "Service"
                    }
                    deviceMonitor = component "Device Monitor" "Background ROS device/topic health monitor thread" "Python" {
                        tags "Service"
                    }
                }

                // NOTE: workflowSM and recordingSM are logical components of dataCollectionService,
                // but are modelled as containers so that dedicated component views can be rendered for their state diagrams.
                // They are excluded from DataCollection-Containers to avoid cluttering that view.
                workflowSM = container "Workflow State Machine" "Manages robot lifecycle transitions: idle → ready → teleop → error (workflow.py)" "Python" {
                    tags "StateMachine"

                    wfIdle = component "IDLE" "System inactive, no robot controller running" "Python" {
                        tags "StateIdle"
                    }
                    wfReady = component "READY" "Robot active but not accepting command input" "Python" {
                        tags "StateReady"
                    }
                    wfSyncing = component "SYNCING" "Robot aligning with teleop device pose" "Python" {
                        tags "StateSyncing"
                    }
                    wfFollowing = component "FOLLOWING" "Robot following teleop device" "Python" {
                        tags "StateFollowing"
                    }
                    wfIdle -> wfReady "get_ready"
                    wfReady -> wfSyncing "start_syncing"
                    wfSyncing -> wfFollowing "start_teleop"
                    wfFollowing -> wfReady "stop_teleop"
                    wfSyncing -> wfReady "stop_teleop"
                    wfReady -> wfIdle "get_idle"
                }

                recordingSM = container "Recording State Machine" "Manages per-episode recording lifecycle: idle → recording → reviewing (recording.py)" "Python" {
                    tags "StateMachine"

                    recIdle = component "IDLE" "Waiting for the operator to start a new episode recording" "Python" {
                        tags "StateIdle"
                    }
                    recRecording = component "RECORDING" "Capturing ROS topics in MCAP for the current episode" "Python" {
                        tags "StateRecording"
                    }
                    recReviewing = component "REVIEWING" "Episode recorded and waiting for label (success, failure, or deletion)" "Python" {
                        tags "StateReviewing"
                    }

                    recIdle -> recRecording "start_recording"
                    recRecording -> recReviewing "stop_recording"
                    recReviewing -> recIdle "mark_success"
                    recReviewing -> recIdle "mark_failure"
                    recReviewing -> recIdle "delete"
                }

                dataRecorderService = container "Data Recorder Service" "ROS 2 microservice for capturing and recording data streams to MCAP format" "ROS 2/FastAPI" {
                    tags "Service"
                }

                dataProcessorService = container "Data Processor Service" "Batch processing daemon for storage-efficient format conversion" "Python" {
                    tags "Service"
                }

                datasetBuilder = container "Dataset Builder" "Export tooling to specific format (e.g., LeRobot)" "Python CLI" {
                    tags "Tooling"
                }

                dataCollectionDB = container "Data Collection DB" "Database storing episode and task metadata" "PostgreSQL" {
                    tags "Database"
                }

                stationConfig = container "Station Config & Metadata" "Configuration files for the robot, cameras, teleoperation devices and collected task" "YAML/JSON" {
                    tags "Config"
                }

                rawStorage = container "Raw Episode Storage" "Raw data based on ROS 2 bags" "File System" {
                    tags "FileStorage"
                }

                processedStorage = container "Processed Episode Storage" "Processed data based on AV1 videos in MCAP format" "File System" {
                    tags "FileStorage"
                }
            }
        }

        group "Model Training Pipeline" {

            modelTraining = softwareSystem "Model Training" "VLA model training framework" {
                tags "AISystem"
                vlaContainer = container "VLA model" "VLA model training framework" "Python/PyTorch" {
                    tags "VLA"
                    dataConfig = component "Data Config" "Training data configuration" "Python" {
                        tags "ConfigComponent"
                    }
                    vlaModel = component "VLA Model" "Vision-language foundation model" "PyTorch" {
                        tags "AIModel"
                    }
                    trainingScripts = component "Training Scripts" "Model fine-tuning scripts" "Python" {
                        tags "TrainingScript"
                    }
                }
                
                lerobotContainer = container "LeRobot Training" "Alternative LeRobot training pipeline" "Python/PyTorch" {
                    tags "TrainingFramework"
                }
                tensorrtContainer = container "TensorRT Engine" "Optimized inference engine" "TensorRT" {
                    tags "TensorRT"
                }
            }

            storageSystem = softwareSystem "Data Storage" "Dataset and model storage" {
                tags "StorageSystem"
                datasets = container "Datasets" "Recorded robot episodes" "File System" {
                    tags "FileStorage"
                }
                checkpoints = container "Model Checkpoints" "Fine-tuned model weights" "File System" {
                    tags "FileStorage"
                }
                huggingface = container "Hugging Face Hub" "Model and dataset repository" "Cloud" {
                    tags "HuggingFace"
                }
            }
        }

        group "Inference Pipeline" {

            inference = softwareSystem "Franka Inference" "Inference for the VLA model at 20Hz based in ROS 2" {
                tags "FrankaSWSystem"
                vlaInferenceContainer = container "franka_learning_vla" "VLA model based inference system" "ROS 2/Python" {
                    tags "ROSPackage"
                    inferenceNode = component "Inference Node" "Main inference control node" "ROS 2/Python" {
                        tags "ROSNode"
                    }
                    policyLoader = component "Policy Loader" "Model checkpoint loader" "Python" {
                        tags "ModelLoader"
                    }
                    actionQueue = component "Action Queue" "Action smoothing and queueing" "Python" {
                        tags "ActionQueue"
                    }
                }
            }


            frankaRobots = softwareSystem "Franka Robot" "Franka FR3, FR3 Duo or Mobile FR3 Duo robot system with its ROS 2 interface" {
                tags "RobotSystem"
                fr3Robot = container "FR3 Robot" "Single arm Franka FR3 robot" "Physical Robot" {
                    tags "PhysicalRobot"
                }
                fr3DuoRobot = container "FR3 Duo" "Dual arm Franka FR3 robot system" "Physical Robot" {
                    tags "PhysicalRobot"
                }
                fr3Follower = container "Franka Follower Controllers" "Follower control stack for Franka robots" "ROS 2" {
                    tags "ROSInterface"
                }
            }
        }

        # User interactions
        user -> dataCollectionUI "Plans, labels, and monitors episodes"
        user -> gelloHardware "Controls robot joint-based movements"
        user -> teleopDevices "Controls robot via custom interface"
        user -> fr3DuoLeader "Controls leader robot"
        user -> stationConfig "Sets station-specific configuration"

        dataCollectionUI -> dataCollectionService "Start/stop teleop and recording, assign tasks and episode management"
        dataCollectionService -> dataCollectionUI "Streams live device health and episode event updates"

        # Core service interactions
        dataCollectionService -> dataCollectionDB "Persists episode and task metadata"
        dataCollectionService -> stationConfig "Loads station configuration"
        dataCollectionService -> workflowSM "Drives workflow transitions"
        dataCollectionService -> recordingSM "Drives recording transitions"
        dataCollectionService -> dataRecorderService "Start/stop recording via REST"
        dataProcessorService -> dataCollectionService "Polls episode processed status"
        // datasetBuilder -> dataCollectionService "Fetches manifests & tags"

        # Teleoperation & sensing data flow
        // gelloSoftware -> dataRecorderService "Publishes joint states (ROS 2 topics)"
        // fr3Teleop -> dataRecorderService "Publishes leader robot states"
        // teleopDrivers -> dataRecorderService "Publishes device-specific commands"
        teleopSystem -> dataRecorderService "Publishes device states and commands"
        fr3Robot -> dataRecorderService "Publishes robot state (ROS 2 topics)"

        # Camera data flow
        // headCamera -> dataRecorderService "Publishes camera feeds"
        // wristCameras -> dataRecorderService "Publishes camera feeds"
        // bodyCamera -> dataRecorderService "Publishes camera feeds"
        cameraDrivers -> dataRecorderService "Publishes camera feeds"

        # Episode storage & processing
        dataRecorderService -> rawStorage "Writes raw ROS 2 bag data"
        dataProcessorService -> rawStorage "Reads raw ROS 2 bag data"
        dataProcessorService -> processedStorage "Writes processed MCAP data"
        datasetBuilder -> processedStorage "Reads processed episodes"
        datasetBuilder -> datasets "Uploads formatted datasets"
        datasetBuilder -> huggingface "Publishes public dataset releases"

        # Training flow
        datasets -> dataConfig "Loads training data"
        trainingScripts -> vlaModel "Fine-tunes model"
        vlaModel -> checkpoints "Saves model weights"
        checkpoints -> huggingface "Uploads checkpoints"
        checkpoints -> tensorrtContainer "Creates optimized engine"

        # Inference flow
        checkpoints -> policyLoader "Loads fine-tuned model"
        cameraDrivers -> inferenceNode "Provides visual input"
        inferenceNode -> actionQueue "Generates actions"
        fr3DuoRobot -> vlaInferenceContainer "Reports current state"
        vlaInferenceContainer -> fr3DuoRobot "Executes control actions"
    }

    views {
        systemLandscape "SystemLandscape" {
            include *
            autoLayout tb
        }

        systemContext dataCollectionPlatform "DataCollection-Context" {
            include user
            include storageSystem
            include teleopSystem
            include cameraSystem
            // excluded frankaRobots since it is parted of the inference context, but could be included if desired
            autoLayout tb
        }

        systemContext inference "Inference-Context" {
            include *
            autoLayout lr
        }

        container dataCollectionPlatform "DataCollection-Containers" {
            include *
            exclude workflowSM
            exclude recordingSM
            // autoLayout lr
        }

        container inference "Inference-Containers" {
            include *
            autoLayout lr
        }

        container modelTraining "Training-Containers" {
            include *
            autoLayout lr
        }

        component dataCollectionService "DataCollectionService-Components" {
            include *
            autoLayout lr
        }

        component workflowSM "WorkflowStateMachine" "Workflow state machine" {
            include *
            // autoLayout lr
        }

        component recordingSM "RecordingStateMachine" "Recording state machine" {
            include *
            autoLayout lr
        }

        component vlaInferenceContainer "Inference-Components" {
            include *
            autoLayout lr
        }

        dynamic dataCollectionPlatform "DataRecording-Flow" "Data recording workflow" {
            user -> dataCollectionUI "Plans session and requests recording"
            dataCollectionUI -> dataCollectionService "Sends start recording command"
            dataCollectionService -> dataRecorderService "Issues start to ROS bag service"
            dataRecorderService -> rawStorage "Writes ROS 2 bag data + metadata"
            dataProcessorService -> rawStorage "Pulls raw ROS 2 bag data"
            dataProcessorService -> processedStorage "Stores processed ROS 2 bag data"
            datasetBuilder -> processedStorage "Reads processed episode bundle"
            datasetBuilder -> datasets "Uploads curated dataset"
            autoLayout lr
        }

        dynamic modelTraining "Training-Flow" "Model training workflow" {
            datasets -> vlaContainer "Loads demonstration data"
            vlaContainer -> checkpoints "Saves fine-tuned model"
            checkpoints -> tensorrtContainer "Optimizes for inference"
            autoLayout lr
        }

        dynamic inference "Inference-Flow" "Autonomous execution workflow" {
            checkpoints -> vlaInferenceContainer "Loads fine-tuned policy"
            cameraDrivers -> vlaInferenceContainer "Provides visual input"
            fr3DuoRobot -> vlaInferenceContainer "Reports current state"
            vlaInferenceContainer -> fr3DuoRobot "Executes action"
            autoLayout lr
        }

        styles {
            element "Person" {
                color #ffffff
                background #08427b
                shape Person
            }
            element "Software System" {
                background #1168bd
                color #ffffff
            }
            element "Container" {
                background #438dd5
                color #ffffff
            }
            element "Component" {
                background #85bbf0
                color #000000
            }
            element "WebApp" {
                background #2d88ef
                color #ffffff
            }
            element "Service" {
                background #1b2f36
                color #ffffff
            }
            element "Tooling" {
                background #607d8b
                color #ffffff
            }
            element "Database" {
                background #8d6e63
                color #ffffff
                shape Cylinder
            }
            element "Config" {
                background #abdda4
                color #000000
            }
            
            # Hardware elements
            element "PhysicalRobot" {
                background #dee3e3
                color #1b2f36
                shape Robot
            }
            element "HapticDevice" {
                background #dee3e3
                color #1f77b4
                shape Component
            }
            element "CameraHardware" {
                background #dee3e3
                color #29b6f6
            }
            element "InputDevice" {
                background #dee3e3
                color #1f77b4
            }
            element "CustomDevice" {
                background #dee3e3
                color #1f77b4
            }
            
            # Software elements
            element "ROSPackage" {
                background #23294e
                color #ffffff
            }
            element "ROSNode" {
                background #23294e
                color #ffffff
            }
            element "ROSDriver" {
                background #23294e
                color #ffffff
            }
            element "ROSInterface" {
                background #23294e
                color #ffffff
            }
            element "ConfigLibrary" {
                background #5260B6
                color #ffffff
            }
            // element "ControlInterface" {
            //     background #26c6da
            //     color #ffffff
            // }
            // element "InferenceNode" {
            //     background #5aae61
            //     color #ffffff
            // }
            
            # AI/ML elements
            element "AIModel" {
                background #ff7043
                color #ffffff
                shape Component
            }
            element "VLA" {
                background #ff7043
                color #ffffff
            }
            element "TrainingFramework" {
                background #ff7043
                color #ffffff
            }
            element "TensorRT" {
                background #762a83
                color #ffffff
            }
            element "TrainingScript" {
                background #ff7043
                color #ffffff
            }
            element "ModelLoader" {
                background #ff7043
                color #ffffff
            }
            element "ActionQueue" {
                background #ff7043
                color #ffffff
            }
            
            # Configuration elements
            element "ConfigComponent" {
                background #abdda4
                color #000000
            }
            element "DataHandler" {
                background #abdda4
                color #000000
            }
            element "InterfaceLibrary" {
                background #abdda4
                color #000000
            }
            
            # Storage elements
            element "FileStorage" {
                background #cccccc
                color #000000
                shape Cylinder
            }
            element "HuggingFace" {
                background #fdbd19
                color #ffffff
                shape Cylinder
            }
            
            # System categories
            element "TeleopDevice" {
                background #1f77b4
                color #ffffff
            }
            element "RobotSystem" {
                background #dee3e3
                color #1b2f36
            }
            element "FrankaSWSystem" {
                background #1b2f36
                color #ffffff
            }
            element "AISystem" {
                background #ff7043
                color #ffffff
            }
            element "StorageSystem" {
                background #455A64
                color #ffffff
                shape Cylinder
            }
            element "SensorSystem" {
                background #29b6f6
                color #ffffff
            }

            # State machine containers
            element "StateMachine" {
                background #37474f
                color #ffffff
            }

            # State machine states
            element "StateIdle" {
                background #eceff1
                color #455a64
                shape RoundedBox
            }
            element "StateReady" {
                background #1565c0
                color #ffffff
                shape RoundedBox
            }
            element "StateSyncing" {
                background #f57c00
                color #ffffff
                shape RoundedBox
            }
            element "StateFollowing" {
                background #2e7d32
                color #ffffff
                shape RoundedBox
            }
            element "StateError" {
                background #c62828
                color #ffffff
                shape RoundedBox
            }
            element "StateRecording" {
                background #ad1457
                color #ffffff
                shape RoundedBox
            }
            element "StateReviewing" {
                background #6a1b9a
                color #ffffff
                shape RoundedBox
            }
        }
    }
}
