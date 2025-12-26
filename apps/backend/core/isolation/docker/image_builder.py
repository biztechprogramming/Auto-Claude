"""
Docker image builder for Auto-Claude containers.

Handles building Docker images for the multi-container pipeline.
Separated from orchestrator to allow standalone image building.
"""

import os
import subprocess
from pathlib import Path
from typing import Optional

from ..base import ContainerRole


class ImageBuilder:
    """
    Builds Docker images for Auto-Claude containers.

    Responsibilities:
    - Build base image
    - Build role-specific images (developer, evaluator, QA)
    - Check if images exist
    - Respect DOCKER_ALWAYS_REBUILD configuration
    """

    # Default image names
    DEFAULT_IMAGE_BASE = "auto-claude-base:latest"
    DEFAULT_IMAGE_DEVELOPER = "auto-claude-dev:latest"
    DEFAULT_IMAGE_EVALUATOR = "auto-claude-eval:latest"
    DEFAULT_IMAGE_QA = "auto-claude-qa:latest"

    def __init__(self):
        """Initialize the image builder."""
        # Paths relative to this file's location
        # This file is in: apps/backend/core/isolation/docker/image_builder.py
        # We need: apps/backend/docker/ for Dockerfiles
        # We need: apps/backend/ for build context
        self.dockerfile_dir = Path(__file__).parent.parent.parent.parent / "docker"
        self.build_context = Path(__file__).parent.parent.parent.parent

    def image_exists(self, image_name: str) -> bool:
        """
        Check if a Docker image exists locally.

        Args:
            image_name: Name of the image to check

        Returns:
            True if image exists, False otherwise
        """
        result = subprocess.run(
            ["docker", "images", "-q", image_name],
            capture_output=True,
            text=True,
        )
        return bool(result.stdout.strip())

    def build_image(
        self,
        image_name: str,
        dockerfile: Path,
        force: bool = False,
    ) -> None:
        """
        Build a single Docker image.

        Args:
            image_name: Name to tag the built image
            dockerfile: Path to the Dockerfile
            force: If True, always rebuild. If False, only build if image doesn't exist
                   or if DOCKER_ALWAYS_REBUILD=true in .env

        Raises:
            subprocess.CalledProcessError: If docker build fails
        """
        # Check configuration
        always_rebuild = os.environ.get("DOCKER_ALWAYS_REBUILD", "false").lower() == "true"
        should_build = force or always_rebuild

        if not dockerfile.exists():
            raise FileNotFoundError(f"Dockerfile not found: {dockerfile}")

        if should_build or not self.image_exists(image_name):
            print(f"Building {image_name}... (force={force}, always_rebuild={always_rebuild})")
            subprocess.run(
                [
                    "docker", "build",
                    "-f", str(dockerfile),
                    "-t", image_name,
                    str(self.build_context),
                ],
                check=True,
            )
        else:
            print(f"{image_name} exists, skipping build (set DOCKER_ALWAYS_REBUILD=true to force)")

    def build_all_images(
        self,
        images: Optional[dict[ContainerRole, str]] = None,
        force: bool = False,
    ) -> None:
        """
        Build all required Docker images.

        Args:
            images: Optional dict mapping roles to image names. If not provided,
                    uses default image names.
            force: If True, always rebuild. If False, only build if images don't exist
                   or if DOCKER_ALWAYS_REBUILD=true in .env

        Raises:
            subprocess.CalledProcessError: If any docker build fails
        """
        # Use default images if none provided
        if images is None:
            images = {
                ContainerRole.DEVELOPER: self.DEFAULT_IMAGE_DEVELOPER,
                ContainerRole.EVALUATOR: self.DEFAULT_IMAGE_EVALUATOR,
                ContainerRole.QA: self.DEFAULT_IMAGE_QA,
            }

        # Build base image first
        base_image = self.DEFAULT_IMAGE_BASE
        base_dockerfile = self.dockerfile_dir / "Dockerfile.base"

        if base_dockerfile.exists():
            self.build_image(base_image, base_dockerfile, force=force)
        else:
            print(f"Warning: Base Dockerfile not found at {base_dockerfile}")

        # Build role-specific images
        for role, image in images.items():
            dockerfile = self.dockerfile_dir / f"Dockerfile.{role.value}"
            if dockerfile.exists():
                self.build_image(image, dockerfile, force=force)
            else:
                print(f"Warning: Dockerfile not found at {dockerfile}")

    def get_default_images(self) -> dict[ContainerRole, str]:
        """
        Get the default image names for all roles.

        Returns:
            Dict mapping ContainerRole to default image name
        """
        return {
            ContainerRole.DEVELOPER: self.DEFAULT_IMAGE_DEVELOPER,
            ContainerRole.EVALUATOR: self.DEFAULT_IMAGE_EVALUATOR,
            ContainerRole.QA: self.DEFAULT_IMAGE_QA,
        }
