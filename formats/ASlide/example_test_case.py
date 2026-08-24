"""
ASlide Complete Feature Test Suite
Demonstrates all supported formats and features
"""

from Aslide import Slide
from Aslide.bootstrap import setup_runtime_environment
from Aslide.deepzoom import DeepZoom
import os


setup_runtime_environment()


def test_basic_functionality(slide_path):
    """Test basic functionality common to all formats"""
    print(f"\n{'=' * 80}")
    print(f"Testing file: {slide_path}")
    print(f"{'=' * 80}")

    try:
        with Slide(slide_path) as slide:
            # 1. Basic properties
            print(f"\n[Basic Properties]")
            print(f"  Format: {slide.format}")
            print(f"  Level 0 dimensions: {slide.dimensions}")
            print(f"  Level count: {slide.level_count}")
            print(f"  All level dimensions: {slide.level_dimensions}")
            print(f"  Downsample factors: {slide.level_downsamples}")

            # 2. MPP (microns per pixel)
            try:
                mpp = slide.mpp
                print(f"  MPP: {mpp:.4f} μm/pixel")
            except Exception as e:
                print(f"  MPP: Not available ({e})")

            # 3. Metadata
            print(f"\n[Metadata] (first 10 properties)")
            for i, (key, value) in enumerate(slide.properties.items()):
                if i >= 10:
                    print(f"  ... (total {len(slide.properties)} properties)")
                    break
                # Truncate long values
                value_str = str(value)[:100]
                print(f"  {key}: {value_str}")

            # 4. Associated images
            print(f"\n[Associated Images]")
            assoc_images = slide.associated_images
            if assoc_images:
                for name, img in assoc_images.items():
                    if hasattr(img, "size"):
                        print(f"  {name}: {img.size}")
                    else:
                        print(f"  {name}: {type(img)}")
            else:
                print(f"  No associated images")

            # 5. Best level calculation
            print(f"\n[Best Level for Downsample]")
            for downsample in [4, 16, 64]:
                best_level = slide.get_best_level_for_downsample(downsample)
                print(f"  Downsample {downsample}x: Level {best_level}")

            # 6. Read region
            print(f"\n[Read Region Test]")
            if slide.slide_family == "multiplex":
                biomarkers = slide.list_biomarkers()
                print(f"  Biomarker count: {len(biomarkers)}")
                print(f"  First biomarkers: {biomarkers[:5]}")
                region = slide.read_biomarker_region(
                    (0, 0), 0, (512, 512), biomarkers[0]
                )
                print(f"  Region size: {region.size}")
                print(f"  Image mode: {region.mode}")
                output_path = f"test_output_{os.path.basename(slide_path)}_{biomarkers[0]}_region.png"
                region.save(output_path)
                print(f"  Saved to: {output_path}")
                print(
                    f"  Selected acquisition: {slide.properties.get('mcd.selected-acquisition-description')}"
                )
            else:
                region = slide.read_region((0, 0), 0, (512, 512))
                print(f"  Region size: {region.size}")
                print(f"  Image mode: {region.mode}")
                output_path = f"test_output_{os.path.basename(slide_path)}_region.png"
                region.save(output_path)
                print(f"  Saved to: {output_path}")

                # 7. Thumbnail
                print(f"\n[Thumbnail]")
                thumbnail = slide.get_thumbnail((500, 500))
                print(f"  Thumbnail size: {thumbnail.size}")
                thumb_path = f"test_output_{os.path.basename(slide_path)}_thumb.png"
                thumbnail.save(thumb_path)
                print(f"  Saved to: {thumb_path}")

            print(f"\nBasic functionality test completed")

    except Exception as e:
        print(f"\nError: {e}")
        import traceback

        traceback.print_exc()


def test_qptiff_biomarkers(slide_path):
    print(f"\n{'=' * 80}")
    print(f"QPTiff Multi-channel Test: {slide_path}")
    print(f"{'=' * 80}")

    try:
        with Slide(slide_path) as slide:
            # Check if QPTiff format
            if slide.format.lower() not in [".qptiff"]:
                print(f"Skipped: Not QPTiff format (current: {slide.format})")
                return

            print(f"\n[QPTIFF Classification]")
            print(f"  slide_family: {slide.slide_family}")

            if slide.slide_family == "brightfield":
                region = slide.read_region((0, 0), 0, (512, 512))
                print(f"  Brightfield region: {region.size}, {region.mode}")
                output_path = "test_output_qptiff_brightfield.png"
                region.save(output_path)
                print(f"  Saved to: {output_path}")
            else:
                biomarkers = slide.list_biomarkers()
                print(f"\n[Biomarker Channels]")
                print(f"  Available channels: {biomarkers}")
                print(f"  Channel count: {len(biomarkers)}")

                print(f"\n[Individual Channel Read]")
                for biomarker in biomarkers:
                    region = slide.read_biomarker_region(
                        location=(0, 0), level=0, size=(512, 512), biomarker=biomarker
                    )
                    print(f"  {biomarker}: {region.size}, {region.mode}")
                    output_path = f"test_output_qptiff_{biomarker}.png"
                    region.save(output_path)
                    print(f"    Saved to: {output_path}")

            print(f"\nQPTiff runtime classification test completed")

    except Exception as e:
        print(f"\nError: {e}")
        import traceback

        traceback.print_exc()


def test_mcd_acquisition_selection(slide_path, acquisition_id=2):
    print(f"\n{'=' * 80}")
    print(f"MCD Acquisition Selection Test: {slide_path}")
    print(f"{'=' * 80}")

    try:
        with Slide(slide_path, acquisition_id=acquisition_id) as slide:
            if slide.format.lower() != ".mcd":
                print(f"Skipped: Not MCD format (current: {slide.format})")
                return

            print(f"  slide_family: {slide.slide_family}")
            print(
                f"  selected acquisition id: {slide.properties.get('mcd.selected-acquisition-id')}"
            )
            print(
                f"  selected acquisition description: {slide.properties.get('mcd.selected-acquisition-description')}"
            )
            print(f"  dimensions: {slide.dimensions}")
            biomarkers = slide.list_biomarkers()
            print(f"  first biomarkers: {biomarkers[:5]}")

    except Exception as e:
        print(f"\nError: {e}")
        import traceback

        traceback.print_exc()


def test_sdpc_advanced(slide_path):
    """Test SDPC format advanced features"""
    print(f"\n{'=' * 80}")
    print(f"SDPC Advanced Features Test: {slide_path}")
    print(f"{'=' * 80}")

    try:
        with Slide(slide_path) as slide:
            if slide.format.lower() not in [".sdpc"]:
                print(f"Skipped: Not SDPC format (current: {slide.format})")
                return

            print(f"\n[SDPC-Specific Features]")

            # 1. Barcode
            try:
                barcode = slide.backend.get_barcode()
                print(f"  Barcode: {barcode if barcode else 'Not available'}")
            except Exception as e:
                print(f"  Barcode: Error ({e})")

            # 2. Slide type
            try:
                slide_type = slide.backend.get_slide_type()
                print(f"  Slide type: {slide_type}")
            except Exception as e:
                print(f"  Slide type: Error ({e})")

            # 3. Channel count
            try:
                channel_count = slide.backend.get_channel_count()
                print(f"  Channel count: {channel_count}")
            except Exception as e:
                print(f"  Channel count: Error ({e})")

            # 4. Focal plane info
            try:
                plane_count = slide.backend.get_plane_count()
                plane_spacing = slide.backend.get_plane_space_between()
                print(f"  Focal planes: {plane_count}")
                print(f"  Plane spacing: {plane_spacing} μm")
            except Exception as e:
                print(f"  Focal plane info: Error ({e})")

            # 5. Tile size
            try:
                tile_size = slide.backend.get_tile_size()
                print(f"  Tile size: {tile_size}")
            except Exception as e:
                print(f"  Tile size: Error ({e})")

            # 6. Color correction (demonstration only, not applied)
            print(f"\n[Color Correction Options]")
            print(f"  Available styles: 'Real', 'Gorgeous'")
            print(
                f"  Usage: slide.backend.apply_color_correction(apply=True, style='Real')"
            )

            # 7. JPEG quality (demonstration only)
            print(f"\n[JPEG Quality Control]")
            print(f"  Range: 1-99 (higher = better quality)")
            print(f"  Usage: slide.backend.set_jpeg_quality(quality=90)")

            # 8. Label image
            print(f"\n[Label Image]")
            label_path = f"test_output_sdpc_label.png"
            try:
                slide.label_image(save_path=label_path)
                print(f"  Label image saved to: {label_path}")
            except Exception as e:
                print(f"  Label image: Error ({e})")

            print(f"\nSDPC advanced features test completed")

    except Exception as e:
        print(f"\nError: {e}")
        import traceback

        traceback.print_exc()


def test_deepzoom(slide_path):
    """Test DeepZoom functionality"""
    print(f"\n{'=' * 80}")
    print(f"DeepZoom Test: {slide_path}")
    print(f"{'=' * 80}")

    try:
        with Slide(slide_path) as slide:
            print(f"\n[DeepZoom Initialization]")
            if slide.supports_biomarkers:
                biomarker = slide.get_default_display_biomarker()
                dzg = DeepZoom(
                    slide=slide,
                    tile_size=254,
                    overlap=1,
                    limit_bounds=False,
                    biomarker=biomarker,
                )
                print(f"  Selected biomarker: {biomarker}")
            else:
                dzg = DeepZoom(
                    slide=slide, tile_size=254, overlap=1, limit_bounds=False
                )

            # DeepZoom properties
            print(f"  DeepZoom level count: {dzg.level_count}")
            print(f"  Total tile count: {dzg.tile_count}")
            print(f"  Level tiles (first 5): {dzg.level_tiles[:5]}...")
            print(f"  Level dimensions (first 5): {dzg.level_dimensions[:5]}...")

            # Get DZI metadata
            print(f"\n[DZI Metadata]")
            dzi_xml = dzg.get_dzi("jpeg")
            print(f"  DZI XML (first 200 chars):")
            print(f"  {dzi_xml[:200]}...")

            # Save DZI file
            dzi_path = f"test_output_{os.path.basename(slide_path)}.dzi"
            with open(dzi_path, "w") as f:
                f.write(dzi_xml)
            print(f"  Saved to: {dzi_path}")

            # Get sample tiles
            print(f"\n[Sample Tiles]")
            mid_level = dzg.level_count // 2
            tile = dzg.get_tile(mid_level, (0, 0))
            print(f"  Level {mid_level}, tile (0,0): {tile.size}, {tile.mode}")
            tile_path = f"test_output_{os.path.basename(slide_path)}_tile.jpg"
            tile.save(tile_path)
            print(f"  Saved to: {tile_path}")

            print(f"\nDeepZoom test completed")

    except Exception as e:
        print(f"\nError: {e}")
        import traceback

        traceback.print_exc()


def main():
    """Main test function"""
    print("""
╔════════════════════════════════════════════════════════════════════════════╗
║                   ASlide Complete Feature Test Suite                       ║
╚════════════════════════════════════════════════════════════════════════════╝
    """)

    # Test file list - replace with actual file paths
    test_slides = {
        "svs": "path/to/your/slide.svs",
        "ndpi": "path/to/your/slide.ndpi",
        "kfb": "path/to/your/slide.kfb",
        "sdpc": "path/to/your/slide.sdpc",
        "tmap": "path/to/your/slide.tmap",
        "qptiff": "path/to/your/slide.qptiff",
        "isyntax": "path/to/your/slide.isyntax",
        "tron": "path/to/your/slide.tron",
        "vsi": "path/to/your/slide.vsi",
        "mds": "path/to/your/slide.mds",
    }

    # Or use a single file for testing
    single_test_file = "path/to/your/slide.xxx"

    # Select test mode
    print("Test modes:")
    print("1. Test single file (modify single_test_file variable)")
    print("2. Test multiple files (modify test_slides dictionary)")
    print()

    # Single file test example
    if os.path.exists(single_test_file):
        print(f"Starting single file test: {single_test_file}\n")

        # Basic functionality test (all formats)
        test_basic_functionality(single_test_file)

        # DeepZoom test (all formats)
        test_deepzoom(single_test_file)

        # Format-specific tests
        test_qptiff_biomarkers(single_test_file)  # QPTiff only
        test_sdpc_advanced(single_test_file)  # SDPC only
    else:
        print(f"File not found: {single_test_file}")
        print("Please modify single_test_file variable to an actual file path")

    # Multiple file test example (uncomment to use)
    # for format_name, slide_path in test_slides.items():
    #     if os.path.exists(slide_path):
    #         print(f"\nStarting {format_name.upper()} format test\n")
    #         test_basic_functionality(slide_path)
    #         test_deepzoom(slide_path)
    #
    #         # Format-specific tests
    #         if format_name == 'qptiff':
    #             test_qptiff_biomarkers(slide_path)
    #         elif format_name == 'sdpc':
    #             test_sdpc_advanced(slide_path)
    #     else:
    #         print(f"Skipped {format_name}: File not found")

    print(f"\n{'=' * 80}")
    print("All tests completed!")
    print(f"{'=' * 80}\n")


if __name__ == "__main__":
    main()
