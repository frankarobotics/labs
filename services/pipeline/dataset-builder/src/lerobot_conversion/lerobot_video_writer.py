from pathlib import Path

from loguru import logger


class LeRobotVideoWriter:
    """Handles writing video files in the LeRobot directory structure.

    This class creates the appropriate directory hierarchy and writes MP4 video files
    for each camera and episode, organizing them by chunk and camera name.


    """

    def __init__(self, output_dir: Path) -> None:
        """Initialize the LeRobotVideoWriter with the base output directory.

        Args:
            output_dir: Base output directory for LeRobot dataset
        """
        self.videos_dir: Path = output_dir / "videos"
        self.videos_dir.mkdir(parents=True, exist_ok=True)

    def write_video_file(self, video_data: bytes, camera_name: str, episode_index: int, chunk_index: int = 0) -> Path:
        """Write video file in LeRobot structure.

        Args:
            video_data: MP4 video bytes
            camera_name: Camera identifier
            episode_index: Episode number
            chunk_index: Chunk number

        Returns:
            Path to written video file
        """
        # Create camera directory
        camera_dir: Path = self.videos_dir / f"chunk-{chunk_index:03d}" / camera_name
        camera_dir.mkdir(parents=True, exist_ok=True)

        # Write video file
        video_file: Path = camera_dir / f"episode_{episode_index:06d}.mp4"

        with video_file.open("wb") as f:
            f.write(video_data)

        logger.info(f"Wrote video file: {video_file} ({len(video_data)} bytes)")

        return video_file
