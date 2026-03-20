"""Screenshot annotation - adds visual highlights to screenshots."""

import logging
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from config import (
    CIRCLE_RADIUS, CIRCLE_COLOR, CIRCLE_OUTLINE_WIDTH,
    CIRCLE_GLOW_COLOR, CIRCLE_GLOW_RADIUS,
    STEP_BADGE_SIZE, STEP_BADGE_COLOR, STEP_BADGE_TEXT_COLOR,
    CROP_WIDTH, CROP_HEIGHT, THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT,
)

log = logging.getLogger(__name__)


class Annotator:
    """Annotates screenshots with click highlights and step numbers."""

    def annotate_screenshot(
        self,
        screenshot_path: Path,
        click_x: int,
        click_y: int,
        step_number: int,
        output_dir: Path,
    ) -> tuple[Path, Path]:
        """Annotate a screenshot with a highlight circle and step badge.

        Returns:
            Tuple of (annotated_full_path, thumbnail_path)

        Raises:
            OSError: If the screenshot file cannot be opened or saved.
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        img = Image.open(screenshot_path)
        try:
            w, h = img.size
            # Clamp coordinates to image bounds
            cx = max(0, min(click_x, w - 1))
            cy = max(0, min(click_y, h - 1))

            annotated = self._draw_highlight(img.copy(), cx, cy, step_number)
            annotated_path = output_dir / f"annotated_{screenshot_path.name}"
            annotated.save(str(annotated_path), "PNG", optimize=True)

            thumbnail = self._create_thumbnail(annotated, cx, cy)
            thumbnail_path = output_dir / f"thumb_{screenshot_path.name}"
            thumbnail.save(str(thumbnail_path), "PNG", optimize=True)

            # Close intermediate images
            annotated.close()
            thumbnail.close()

            return annotated_path, thumbnail_path
        finally:
            img.close()

    def _draw_highlight(
        self, img: Image.Image, x: int, y: int, step_number: int
    ) -> Image.Image:
        """Draw a glowing circle highlight and step badge on the image."""
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw_overlay = ImageDraw.Draw(overlay)

        glow_bbox = (
            x - CIRCLE_GLOW_RADIUS,
            y - CIRCLE_GLOW_RADIUS,
            x + CIRCLE_GLOW_RADIUS,
            y + CIRCLE_GLOW_RADIUS,
        )
        draw_overlay.ellipse(glow_bbox, fill=CIRCLE_GLOW_COLOR)

        img_rgba = img.convert("RGBA")
        composited = Image.alpha_composite(img_rgba, overlay)
        overlay.close()
        img_rgba.close()

        draw = ImageDraw.Draw(composited)
        circle_bbox = (
            x - CIRCLE_RADIUS,
            y - CIRCLE_RADIUS,
            x + CIRCLE_RADIUS,
            y + CIRCLE_RADIUS,
        )
        draw.ellipse(
            circle_bbox,
            outline=CIRCLE_COLOR,
            width=CIRCLE_OUTLINE_WIDTH,
        )

        self._draw_step_badge(draw, x, y, step_number, composited.size)

        result = composited.convert("RGB")
        composited.close()
        return result

    def _draw_step_badge(
        self,
        draw: ImageDraw.Draw,
        click_x: int,
        click_y: int,
        step_number: int,
        img_size: tuple[int, int],
    ):
        """Draw a numbered badge near the click point."""
        badge_r = STEP_BADGE_SIZE // 2

        badge_x = click_x + CIRCLE_RADIUS + 5
        badge_y = click_y - CIRCLE_RADIUS - 5

        badge_x = max(badge_r, min(badge_x, img_size[0] - badge_r))
        badge_y = max(badge_r, min(badge_y, img_size[1] - badge_r))

        badge_bbox = (
            badge_x - badge_r,
            badge_y - badge_r,
            badge_x + badge_r,
            badge_y + badge_r,
        )
        draw.ellipse(badge_bbox, fill=STEP_BADGE_COLOR)

        text = str(step_number)
        try:
            font = ImageFont.truetype("arial.ttf", STEP_BADGE_SIZE - 10)
        except (OSError, IOError):
            font = ImageFont.load_default()

        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_w = text_bbox[2] - text_bbox[0]
        text_h = text_bbox[3] - text_bbox[1]
        text_x = badge_x - text_w // 2
        text_y = badge_y - text_h // 2 - 2

        draw.text((text_x, text_y), text, fill=STEP_BADGE_TEXT_COLOR, font=font)

    def _create_thumbnail(
        self, img: Image.Image, center_x: int, center_y: int
    ) -> Image.Image:
        """Create a cropped and resized thumbnail centered on the click point."""
        w, h = img.size

        left = max(0, center_x - CROP_WIDTH // 2)
        top = max(0, center_y - CROP_HEIGHT // 2)
        right = min(w, left + CROP_WIDTH)
        bottom = min(h, top + CROP_HEIGHT)

        if right - left < CROP_WIDTH:
            left = max(0, right - CROP_WIDTH)
        if bottom - top < CROP_HEIGHT:
            top = max(0, bottom - CROP_HEIGHT)

        cropped = img.crop((left, top, right, bottom))
        cropped.thumbnail((THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT), Image.LANCZOS)

        return cropped
