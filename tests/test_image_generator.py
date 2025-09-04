#!/usr/bin/env python3
"""
Test Image Generator
Creates various test images for poll testing scenarios.

This module generates different types of test images to thoroughly test
the poll system's image handling capabilities.
"""

import os
import io
import random
import subprocess
import shutil
from typing import Tuple, List, Dict, Any, Optional
from PIL import Image, ImageDraw, ImageFont
import logging

logger = logging.getLogger(__name__)


class TestImageGenerator:
    """Generates various test images for poll testing"""

    def __init__(self, use_real_images: bool = False):
        self.test_images_dir = "tests/test_images"
        self.use_real_images = use_real_images
        self.sample_images_repo = "tests/sample-images"
        self.sample_images_path = os.path.join(self.sample_images_repo, "docs")
        self.real_images_cache = []

        os.makedirs(self.test_images_dir, exist_ok=True)

        if self.use_real_images:
            self._setup_real_images()

        # Image configurations for different test scenarios
        self.image_configs = {
            "small": {"size": (100, 100), "format": "PNG"},
            "medium": {"size": (800, 600), "format": "JPEG"},
            "large": {"size": (1920, 1080), "format": "PNG"},
            "square": {"size": (500, 500), "format": "PNG"},
            "wide": {"size": (1200, 400), "format": "JPEG"},
            "tall": {"size": (400, 1200), "format": "PNG"},
            "tiny": {"size": (50, 50), "format": "PNG"},
            "gif": {"size": (300, 300), "format": "GIF"},
            "webp": {"size": (600, 400), "format": "WEBP"},
        }

        # Color schemes for different test scenarios
        self.color_schemes = {
            "bright": [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)],
            "pastel": [
                (255, 182, 193),
                (173, 216, 230),
                (144, 238, 144),
                (255, 218, 185),
            ],
            "dark": [(64, 64, 64), (128, 0, 0), (0, 128, 0), (0, 0, 128)],
            "monochrome": [
                (255, 255, 255),
                (192, 192, 192),
                (128, 128, 128),
                (64, 64, 64),
            ],
            "neon": [(255, 20, 147), (0, 255, 255), (50, 205, 50), (255, 69, 0)],
        }

    def _setup_real_images(self) -> None:
        """Setup real images from sample-images repository"""
        try:
            # Clone the repository if it doesn't exist
            if not os.path.exists(self.sample_images_repo):
                logger.info("Cloning sample-images repository...")
                subprocess.run(
                    [
                        "git",
                        "clone",
                        "https://github.com/yavuzceliker/sample-images.git",
                        self.sample_images_repo,
                    ],
                    check=True,
                    capture_output=True,
                )
                logger.info("Successfully cloned sample-images repository")

            # Cache available image paths
            if os.path.exists(self.sample_images_path):
                self.real_images_cache = []
                for i in range(1, 2001):  # image-1.jpg to image-2000.jpg
                    image_path = os.path.join(self.sample_images_path, f"image-{i}.jpg")
                    if os.path.exists(image_path):
                        self.real_images_cache.append(image_path)

                logger.info(f"Cached {len(self.real_images_cache)} real images")
            else:
                logger.warning(
                    f"Sample images directory not found: {self.sample_images_path}"
                )

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to clone sample-images repository: {e}")
            self.use_real_images = False
        except Exception as e:
            logger.error(f"Error setting up real images: {e}")
            self.use_real_images = False

    def get_random_real_image(self) -> Optional[Tuple[bytes, str]]:
        """Get a random real image from the sample-images repository"""
        if not self.use_real_images or not self.real_images_cache:
            return None

        try:
            # Select a random image
            image_path = random.choice(self.real_images_cache)
            image_name = os.path.basename(image_path)

            # Read the image file
            with open(image_path, "rb") as f:
                image_data = f.read()

            return (image_data, image_name)

        except Exception as e:
            logger.error(f"Error reading real image: {e}")
            return None

    def cleanup_real_images(self) -> None:
        """Clean up the cloned sample-images repository"""
        try:
            if os.path.exists(self.sample_images_repo):
                shutil.rmtree(self.sample_images_repo)
                logger.info("Cleaned up sample-images repository")
        except Exception as e:
            logger.error(f"Error cleaning up sample-images repository: {e}")

    def create_text_image(
        self,
        text: str,
        size: Tuple[int, int],
        bg_color: Tuple[int, int, int] = (255, 255, 255),
        text_color: Tuple[int, int, int] = (0, 0, 0),
        format: str = "PNG",
    ) -> bytes:
        """Create an image with text"""
        try:
            # Create image
            img = Image.new("RGB", size, bg_color)
            draw = ImageDraw.Draw(img)

            # Try to use a font, fall back to default if not available
            try:
                # Try to find a system font
                font_size = min(size[0], size[1]) // 10
                font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", font_size)
            except (OSError, IOError):
                try:
                    font = ImageFont.load_default()
                except:
                    font = None

            # Calculate text position (centered)
            if font:
                bbox = draw.textbbox((0, 0), text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
            else:
                # Rough estimation if no font available
                text_width = len(text) * 6
                text_height = 11

            x = (size[0] - text_width) // 2
            y = (size[1] - text_height) // 2

            # Draw text
            if font:
                draw.text((x, y), text, fill=text_color, font=font)
            else:
                draw.text((x, y), text, fill=text_color)

            # Save to bytes
            img_bytes = io.BytesIO()
            img.save(img_bytes, format=format, quality=95 if format == "JPEG" else None)
            return img_bytes.getvalue()

        except Exception as e:
            logger.error(f"Error creating text image: {e}")
            # Return a simple colored rectangle as fallback
            return self.create_solid_color_image(size, bg_color, format)

    def create_solid_color_image(
        self,
        size: Tuple[int, int],
        color: Tuple[int, int, int] = (128, 128, 128),
        format: str = "PNG",
    ) -> bytes:
        """Create a solid color image"""
        try:
            img = Image.new("RGB", size, color)
            img_bytes = io.BytesIO()
            img.save(img_bytes, format=format, quality=95 if format == "JPEG" else None)
            return img_bytes.getvalue()
        except Exception as e:
            logger.error(f"Error creating solid color image: {e}")
            # Return minimal PNG as last resort
            return self.create_minimal_png()

    def create_gradient_image(
        self,
        size: Tuple[int, int],
        start_color: Tuple[int, int, int] = (255, 0, 0),
        end_color: Tuple[int, int, int] = (0, 0, 255),
        format: str = "PNG",
    ) -> bytes:
        """Create a gradient image"""
        try:
            img = Image.new("RGB", size)
            draw = ImageDraw.Draw(img)

            # Create horizontal gradient
            for x in range(size[0]):
                ratio = x / size[0]
                r = int(start_color[0] * (1 - ratio) + end_color[0] * ratio)
                g = int(start_color[1] * (1 - ratio) + end_color[1] * ratio)
                b = int(start_color[2] * (1 - ratio) + end_color[2] * ratio)

                draw.line([(x, 0), (x, size[1])], fill=(r, g, b))

            img_bytes = io.BytesIO()
            img.save(img_bytes, format=format, quality=95 if format == "JPEG" else None)
            return img_bytes.getvalue()

        except Exception as e:
            logger.error(f"Error creating gradient image: {e}")
            return self.create_solid_color_image(size, start_color, format)

    def create_pattern_image(
        self,
        size: Tuple[int, int],
        pattern_type: str = "checkerboard",
        colors: Optional[List[Tuple[int, int, int]]] = None,
        format: str = "PNG",
    ) -> bytes:
        """Create a patterned image"""
        if colors is None:
            colors = [(255, 255, 255), (0, 0, 0)]

        try:
            img = Image.new("RGB", size)
            draw = ImageDraw.Draw(img)

            if pattern_type == "checkerboard":
                square_size = 20
                for y in range(0, size[1], square_size):
                    for x in range(0, size[0], square_size):
                        color_index = ((x // square_size) + (y // square_size)) % len(
                            colors
                        )
                        draw.rectangle(
                            [x, y, x + square_size, y + square_size],
                            fill=colors[color_index],
                        )

            elif pattern_type == "stripes":
                stripe_width = 30
                for x in range(0, size[0], stripe_width):
                    color_index = (x // stripe_width) % len(colors)
                    draw.rectangle(
                        [x, 0, x + stripe_width, size[1]], fill=colors[color_index]
                    )

            elif pattern_type == "dots":
                dot_spacing = 40
                dot_radius = 15
                for y in range(dot_radius, size[1], dot_spacing):
                    for x in range(dot_radius, size[0], dot_spacing):
                        color_index = ((x // dot_spacing) + (y // dot_spacing)) % len(
                            colors
                        )
                        draw.ellipse(
                            [
                                x - dot_radius,
                                y - dot_radius,
                                x + dot_radius,
                                y + dot_radius,
                            ],
                            fill=colors[color_index],
                        )

            img_bytes = io.BytesIO()
            img.save(img_bytes, format=format, quality=95 if format == "JPEG" else None)
            return img_bytes.getvalue()

        except Exception as e:
            logger.error(f"Error creating pattern image: {e}")
            return self.create_solid_color_image(
                size, colors[0] if colors else (128, 128, 128), format
            )

    def create_minimal_png(self) -> bytes:
        """Create the smallest possible valid PNG"""
        try:
            img = Image.new("RGB", (1, 1), (255, 255, 255))
            img_bytes = io.BytesIO()
            img.save(img_bytes, format="PNG")
            return img_bytes.getvalue()
        except Exception:
            # Return hardcoded minimal PNG if PIL fails
            return b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\tpHYs\x00\x00\x0b\x13\x00\x00\x0b\x13\x01\x00\x9a\x9c\x18\x00\x00\x00\nIDATx\x9cc\xf8\x00\x00\x00\x01\x00\x01\x00\x00\x00\x00IEND\xaeB`\x82"

    def get_test_image_set(self) -> Dict[str, Dict[str, Any]]:
        """Generate a comprehensive set of test images"""
        test_images = {}

        # Basic size variations
        for name, config in self.image_configs.items():
            size = config["size"]
            format = config["format"]

            # Text image
            test_images[f"{name}_text"] = {
                "data": self.create_text_image(
                    f"Test {name.title()}", size, format=format
                ),
                "filename": f"test_{name}_text.{format.lower()}",
                "description": f"{name.title()} text image ({size[0]}x{size[1]} {format})",
            }

            # Solid color
            test_images[f"{name}_solid"] = {
                "data": self.create_solid_color_image(size, (100, 150, 200), format),
                "filename": f"test_{name}_solid.{format.lower()}",
                "description": f"{name.title()} solid color ({size[0]}x{size[1]} {format})",
            }

        # Special test cases
        special_cases = [
            {
                "name": "very_large",
                "data": self.create_text_image(
                    "Large Test", (2048, 1536), format="JPEG"
                ),
                "filename": "test_very_large.jpg",
                "description": "Very large image (2048x1536 JPEG)",
            },
            {
                "name": "minimal",
                "data": self.create_minimal_png(),
                "filename": "test_minimal.png",
                "description": "Minimal 1x1 PNG",
            },
            {
                "name": "gradient",
                "data": self.create_gradient_image(
                    (600, 400), (255, 0, 0), (0, 0, 255)
                ),
                "filename": "test_gradient.png",
                "description": "Gradient image (600x400 PNG)",
            },
            {
                "name": "checkerboard",
                "data": self.create_pattern_image((400, 400), "checkerboard"),
                "filename": "test_checkerboard.png",
                "description": "Checkerboard pattern (400x400 PNG)",
            },
            {
                "name": "stripes",
                "data": self.create_pattern_image(
                    (500, 300), "stripes", [(255, 0, 0), (255, 255, 255), (0, 0, 255)]
                ),
                "filename": "test_stripes.png",
                "description": "Striped pattern (500x300 PNG)",
            },
            {
                "name": "unicode_text",
                "data": self.create_text_image("测试 🎉 тест", (400, 200)),
                "filename": "test_unicode.png",
                "description": "Unicode text image (400x200 PNG)",
            },
        ]

        for case in special_cases:
            test_images[case["name"]] = {
                "data": case["data"],
                "filename": case["filename"],
                "description": case["description"],
            }

        return test_images

    def get_image_for_scenario(
        self, scenario_type: str, poll_id: Any = None
    ) -> Tuple[bytes, str]:
        """Get appropriate test image for a specific scenario"""
        poll_id_str = str(poll_id) if poll_id is not None else "test"

        # Try to get a real image first if requested and available
        if scenario_type == "real" and self.use_real_images:
            real_image = self.get_random_real_image()
            if real_image:
                return real_image
            # Fall back to generated image if real image fails

        if scenario_type == "small":
            return (
                self.create_text_image(f"Poll {poll_id_str}", (200, 150)),
                f"poll_{poll_id_str}_small.png",
            )

        elif scenario_type == "medium":
            return (
                self.create_text_image(f"Poll {poll_id_str}", (600, 400)),
                f"poll_{poll_id_str}_medium.png",
            )

        elif scenario_type == "large":
            return (
                self.create_gradient_image(
                    (1200, 800), (100, 200, 255), (255, 100, 200)
                ),
                f"poll_{poll_id_str}_large.png",
            )

        elif scenario_type == "pattern":
            return (
                self.create_pattern_image((400, 300), "checkerboard"),
                f"poll_{poll_id_str}_pattern.png",
            )

        elif scenario_type == "unicode":
            return (
                self.create_text_image(f"Poll {poll_id_str} 🎉 测试", (500, 200)),
                f"poll_{poll_id_str}_unicode.png",
            )

        elif scenario_type == "minimal":
            return (self.create_minimal_png(), f"poll_{poll_id_str}_minimal.png")

        else:  # default
            return (
                self.create_text_image(f"Test Poll {poll_id_str}", (400, 300)),
                f"poll_{poll_id_str}_default.png",
            )

    def save_test_images_to_disk(self) -> Dict[str, str]:
        """Save all test images to disk and return file paths"""
        test_images = self.get_test_image_set()
        saved_files = {}

        for name, image_info in test_images.items():
            try:
                file_path = os.path.join(self.test_images_dir, image_info["filename"])
                with open(file_path, "wb") as f:
                    f.write(image_info["data"])
                saved_files[name] = file_path
                logger.info(f"Saved test image: {file_path}")
            except Exception as e:
                logger.error(f"Failed to save test image {name}: {e}")

        return saved_files


# Convenience functions for easy import
def get_test_image_generator(use_real_images: bool = False) -> TestImageGenerator:
    """Get a test image generator instance"""
    return TestImageGenerator(use_real_images=use_real_images)


def get_test_image_for_poll(
    poll_id: Any = None, image_type: str = "default", use_real_images: bool = False
) -> Tuple[bytes, str]:
    """Get a test image for a specific poll"""
    generator = TestImageGenerator(use_real_images=use_real_images)
    return generator.get_image_for_scenario(image_type, poll_id)


def create_test_image_with_text(text: str, size: Tuple[int, int] = (400, 300)) -> bytes:
    """Create a simple test image with text"""
    generator = TestImageGenerator()
    return generator.create_text_image(text, size)
