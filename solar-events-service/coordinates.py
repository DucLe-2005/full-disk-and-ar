"""CLI entry point for adding HGS-derived pixel coordinates."""

from app.services.coordinates_service import CoordinatesService


if __name__ == "__main__":
    CoordinatesService().add_pixel_coordinates()
