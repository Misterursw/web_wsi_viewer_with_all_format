// sqrayslideservice.h: SqraySlide SDK header file.
#pragma once
#include "SlideImage.h"
using namespace SQRAYNS;

/**
 * SqraySlide SDK Interface Categories:
 * - Type definition: Core data structures and enumerations
 * - Basic interfaces: Fundamental slide operations
 * - Label: Label image and thumbnail operations
 * - Properties of slide: Slide metadata and properties
 * - Correlation of level: Level-related parameters and operations
 * - Reading image data: Image data retrieval functions
 * - Extend interfaces: Extended functionality
 * - Color Correction: Color correction and enhancement
 * - Fluorescence channel: Fluorescence imaging support
 */

#pragma region Type definition

#pragma pack(push, 1)
struct SqChannelInfo
{
	int32_t ID;                    // Unique channel identifier maintained internally
	unsigned char Nickname[64];   // Channel name configured during scanning
	unsigned char Cube[64];       // Fixed channel name in the channel table
	int32_t CWL;                  // Center wavelength
	int32_t EXWL;                 // Excitation wavelength
	int32_t CWL_BW;               // Center wavelength bandwidth
};

// Options for continuous tile reading
struct ReadingOptions
{
	int32_t mode = 0;             // Currently defaults to 0
};

// Specifies a region at a given level, measured in tiles
struct TileRect
{
	int32_t X;                    // X-coordinate of region start point
	int32_t Y;                    // Y-coordinate of region start point
	int32_t Width;                // Region width
	int32_t Height;               // Region height
	int32_t Level;                // Specified level
};
#pragma pack(pop)
#pragma endregion

#pragma region Basic interfaces

/// <summary>
/// A method that always returns true. Bool type layout may differ across languages,
/// and without proper handling, incorrect return values may be obtained.
/// </summary>
/// <returns>Always returns true.</returns>
EXTERNC SQRAY_SLIDEBASE_EXPORT
bool sqrayslide_always_true();

/// <summary>
/// Open a slide file.
/// </summary>
/// <param name="fileName">File path.</param>
/// <param name="status">Status code for opening the file. 0 indicates success, others refer to SqError enumeration.</param>
/// <returns>Returns a pointer to the digital slide on success, NULL on failure.</returns>
EXTERNC SQRAY_SLIDEBASE_EXPORT
SlideImage* sqrayslide_open(const char* fileName, int* status);

/// <summary>
/// Open a slide file with explicitly specified format.
/// </summary>
/// <param name="fileName">File path.</param>
/// <param name="status">Status code for opening the file. 0 indicates success, others refer to SqError enumeration.</param>
/// <param name="format">Slide format: -1 for internal inference, 0 for SDPC-like format, 1 for DICOM-like format, 2 for DCMZ-like format.</param>
/// <returns>Returns a pointer to the digital slide on success, NULL on failure.</returns>
EXTERNC SQRAY_SLIDEBASE_EXPORT
SlideImage* sqrayslide_open2(const char* fileName, int* status, int format);

/// <summary>
/// Free array memory allocated by library functions.
/// </summary>
/// <param name="array">Array memory allocated by library functions.</param>
EXTERNC SQRAY_SLIDEBASE_EXPORT
void sqrayslide_free_memory(unsigned char* array);

/// <summary>
/// Close a slide.
/// </summary>
/// <param name="slide">Slide pointer.</param>
EXTERNC SQRAY_SLIDEBASE_EXPORT
void sqrayslide_close(SlideImage* slide);
#pragma endregion

#pragma region Label


/// <summary>
/// Get slide-related label, thumbnail, or macro image information.
/// The returned image data is not affected by color correction or channel selection.
/// </summary>
/// <param name="slide">Slide pointer.</param>
/// <param name="imageType">0 for label image; 1 for thumbnail; 2 for macro image.</param>
/// <param name="width">Image width.</param>
/// <param name="height">Image height.</param>
/// <param name="data">JPEG data.</param>
/// <param name="dataSize">JPEG data size.</param>
/// <returns>Returns true on successful image retrieval, false on failure or if image does not exist.</returns>
EXTERNC SQRAY_SLIDEBASE_EXPORT
bool sqrayslide_read_label_jpeg(SlideImage* slide, int imageType, int32_t* width, int32_t* height, unsigned char** data, int32_t* dataSize);
#pragma endregion

#pragma region Properties of slide
/// <summary>
/// Get slide type: brightfield or fluorescence.
/// </summary>
/// <param name="slide">Slide pointer.</param>
/// <returns>Slide type.</returns>
EXTERNC SQRAY_SLIDEBASE_EXPORT
WSI_TYPE sqrayslide_get_type(SlideImage* slide);

/// <summary>
/// Get tile size.
/// </summary>
/// <param name="slide">Slide pointer.</param>
/// <param name="width">Tile width.</param>
/// <param name="height">Tile height.</param>
EXTERNC SQRAY_SLIDEBASE_EXPORT
void sqrayslide_get_tile_size(SlideImage* slide, int32_t* width, int32_t* height);

/// <summary>
/// Get the physical distance represented by each pixel in x and y directions, in micrometers (μm).
/// </summary>
/// <param name="slide">Slide pointer.</param>
/// <param name="x">Distance in x direction.</param>
/// <param name="y">Distance in y direction.</param>
EXTERNC SQRAY_SLIDEBASE_EXPORT
void sqrayslide_get_mpp(SlideImage* slide, double* x, double* y);

/// <summary>
/// Get scanning magnification.
/// </summary>
/// <param name="slide">Slide pointer.</param>
/// <param name="magnification">Scanning magnification.</param>
EXTERNC SQRAY_SLIDEBASE_EXPORT
void sqrayslide_get_magnification(SlideImage* slide, float* magnification);

/// <summary>
/// Get slide barcode. Returns NULL if not present. The string memory is managed by slide, no manual release needed.
/// </summary>
/// <param name="slide">Slide pointer.</param>
/// <returns>Returns barcode on success, NULL on failure or if not present.</returns>
EXTERNC SQRAY_SLIDEBASE_EXPORT
const char* sqrayslide_get_barcode(SlideImage* slide);
#pragma endregion

#pragma region Correlation of level
/*
 * Levels in a slide are represented by numbers in the interval [0, levelCount).
 * The level numbers directly map to positions in the image pyramid:
 * 0 represents the lowest level, levelCount - 1 represents the highest level.
 */

/// <summary>
/// Get the number of levels.
/// </summary>
/// <param name="slide">Slide pointer.</param>
/// <returns>Number of levels.</returns>
EXTERNC SQRAY_SLIDEBASE_EXPORT
int32_t sqrayslide_get_level_count(SlideImage* slide);

/// <summary>
/// Get level image size, including padding.
/// </summary>
/// <param name="slide">Slide pointer.</param>
/// <param name="level">Specified level.</param>
/// <param name="width">Image width.</param>
/// <param name="height">Image height.</param>
EXTERNC SQRAY_SLIDEBASE_EXPORT
void sqrayslide_get_level_size(SlideImage* slide, int32_t level, int32_t* width, int32_t* height);

/// <summary>
/// Get the padding size at the right and bottom edges of the level image.
/// </summary>
/// <param name="slide">Slide pointer.</param>
/// <param name="level">Specified level.</param>
/// <param name="right">Right edge padding size.</param>
/// <param name="buttom">Bottom edge padding size.</param>
EXTERNC SQRAY_SLIDEBASE_EXPORT
void sqrayslide_get_level_right_buttom_bounds_size(SlideImage* slide, int32_t level, int32_t* right, int32_t* buttom);

/// <summary>
/// Get the number of tiles at a level.
/// </summary>
/// <param name="slide">Slide pointer.</param>
/// <param name="level">Specified level.</param>
/// <param name="xCount">Number of tiles in x direction.</param>
/// <param name="yCount">Number of tiles in y direction.</param>
EXTERNC SQRAY_SLIDEBASE_EXPORT
void sqrayslide_get_level_tile_count(SlideImage* slide, int32_t level, int32_t* xCount, int32_t* yCount);

/// <summary>
/// Get the downsample factor.
/// </summary>
/// <param name="slide">Slide pointer.</param>
/// <param name="level">Specified level.</param>
/// <returns>Downsample factor.</returns>
EXTERNC SQRAY_SLIDEBASE_EXPORT
double sqrayslide_get_level_downsample(SlideImage* slide, int32_t level);

/// <summary>
/// Get the best level for a given downsample factor.
/// </summary>
/// <param name="slide">Slide pointer.</param>
/// <param name="downsample">Downsample factor.</param>
/// <returns>Best level.</returns>
EXTERNC SQRAY_SLIDEBASE_EXPORT
int32_t sqrayslide_get_best_level_for_downsample(SlideImage* slide, double downsample);
#pragma endregion

#pragma region Reading image data
/*
 * In the interface, bgra specifically refers to unsigned char* type bgra image data,
 * arranged as b1, g1, r1, a1, b2, g2, r2, a2...
 */

/// <summary>
/// Get image region in BGRA format. For fluorescence slides, outputs pseudo-color image fused from all channels.
/// </summary>
/// <param name="slide">Slide pointer.</param>
/// <param name="dest">Image region BGRA data.</param>
/// <param name="x">X-coordinate of region start point (pixel matrix, unit: pixels).</param>
/// <param name="y">Y-coordinate of region start point (pixel matrix, unit: pixels).</param>
/// <param name="w">Region width (pixel matrix, unit: pixels).</param>
/// <param name="h">Region height (pixel matrix, unit: pixels).</param>
/// <param name="level">Specified level.</param>
/// <returns>Success or failure.</returns>
EXTERNC SQRAY_SLIDEBASE_EXPORT
bool sqrayslide_read_region_bgra(SlideImage* slide, unsigned char* dest, int32_t x, int32_t y, int32_t w, int32_t h, int32_t level);

/// <summary>
/// Get tile in BGRA format. For fluorescence slides, outputs pseudo-color image fused from all channels.
/// </summary>
/// <param name="slide">Slide pointer.</param>
/// <param name="dest">Tile BGRA data.</param>
/// <param name="x">Tile X coordinate (tile matrix, unit: tiles).</param>
/// <param name="y">Tile Y coordinate (tile matrix, unit: tiles).</param>
/// <param name="level">Specified level.</param>
/// <returns>Success or failure.</returns>
EXTERNC SQRAY_SLIDEBASE_EXPORT
bool sqrayslide_read_tile_bgra(SlideImage* slide, unsigned char* dest, int32_t x, int32_t y, int32_t level);

/// <summary>
/// Get tile in JPEG format. Returns -1 on failure. For fluorescence slides, outputs pseudo-color image fused from all channels.
/// </summary>
/// <param name="slide">Slide pointer.</param>
/// <param name="dest">Tile JPEG data.</param>
/// <param name="x">Tile X coordinate (tile matrix, unit: tiles).</param>
/// <param name="y">Tile Y coordinate (tile matrix, unit: tiles).</param>
/// <param name="level">Specified level.</param>
/// <returns>Returns JPEG size on success, -1 on failure.</returns>
EXTERNC SQRAY_SLIDEBASE_EXPORT
int32_t sqrayslide_read_tile_jpeg(SlideImage* slide, unsigned char** dest, int32_t x, int32_t y, int32_t level);

#pragma endregion

#pragma region Extend interfaces

/// <summary>
/// Compress BGRA to JPEG format.
/// </summary>
/// <param name="bgra">Input BGRA data.</param>
/// <param name="dstSize">JPEG size.</param>
/// <param name="quality">Compression quality, 1-99, higher values produce clearer images.</param>
/// <param name="width">Image width.</param>
/// <param name="height">Image height.</param>
/// <returns>Returns JPEG data on success, null on failure.</returns>
EXTERNC SQRAY_SLIDEBASE_EXPORT
unsigned char* sqrayslide_bgra_to_jpeg(unsigned char* bgra, int32_t* dstSize, int32_t quality, int32_t width, int32_t height);

/// <summary>
/// Set compression quality. This parameter specifies the compression quality when slide outputs JPEG.
/// This interface is not thread-safe with image data output interfaces.
/// </summary>
/// <param name="slide">Slide pointer.</param>
/// <param name="quality">Compression quality, 0 to 99, higher values produce clearer images.</param>
EXTERNC SQRAY_SLIDEBASE_EXPORT
void sqrayslide_set_jpeg_quality(SlideImage* slide, int32_t quality);

/// <summary>
/// Pass in a rectangular region in tile units, continuously obtain JPEG image data of all tiles within the rectangular region through callback function fptr.
/// The fptr callback function returns individual tile image data in order from left to right, then top to bottom, calling back slideRectW * slideRectH times in total.
/// If no tile exists at that position or the position is out of bounds, the passed jpg will be empty.
/// This interface attempts to utilize GPU. Some strategies can be changed through the mode parameter. This interface is not currently released.
/// </summary>
/// <param name="slide">Slide pointer.</param>
/// <param name="tileRect">Region to retrieve, measured in tile units.</param>
/// <param name="fptr">Callback function that returns tile image data one by one. jpg represents image data, jpgSize represents the size of image data.</param>
/// <param name="options">Reading options.</param>
/// <returns>Returns -1 on call failure, fptr callback function will not be called; returns 1 on successful call.</returns>
//EXTERNC SQRAY_SLIDEBASE_EXPORT
//int sqrayslide_reading_tiles_jpeg(SlideImage* slide, TileRect tileRect, void (*fptr)(unsigned char* jpg, int jpgSize), ReadingOptions options);

#pragma endregion

#pragma region Color Correction
/// <summary>
/// Apply or cancel color correction for tiles or ROI regions output by slide. Default is not applied. Not applicable to fluorescence images.
/// </summary>
/// <param name="slide">Slide pointer.</param>
/// <param name="apply">When true, color correction will be applied to output tiles.</param>
/// <param name="style">Color correction style.</param>
EXTERNC SQRAY_SLIDEBASE_EXPORT
void sqrayslide_apply_color_correction(SlideImage* slide, bool apply, ColorStyle style = ColorStyle::Real);
#pragma endregion

#pragma region Fluorescence channel
/*
 * Multiple channels exist in Sqray Dicom WSI fluorescence images.
 * Channels in a slide are represented by numbers in the interval [0, channelCount),
 * but the numbers representing channels are only logical identifiers for channels in that slide.
 */

/// <summary>
/// Get channel count. Returns 1 for brightfield images.
/// </summary>
/// <param name="slide">Slide pointer.</param>
/// <returns>Channel count.</returns>
EXTERNC SQRAY_SLIDEBASE_EXPORT
int32_t sqrayslide_get_channel_count(SlideImage* slide);

/// <summary>
/// Get channel information.
/// </summary>
/// <param name="slide">Slide pointer.</param>
/// <param name="channel">Channel logical index.</param>
/// <param name="cnelInfo">Channel information.</param>
/// <returns>Returns false for brightfield type slides.</returns>
EXTERNC SQRAY_SLIDEBASE_EXPORT
bool sqrayslide_get_channel_Info(SlideImage* slide, int32_t channel, SqChannelInfo* cnelInfo);

/*****************************************************************************************************
 * ↓ Brightfield slides calling the following interfaces will all return failure,
 *   multi-channel interfaces all return pseudo-color images. ↓
 *****************************************************************************************************/

/// <summary>
/// Get fluorescence image specific channel thumbnail.
/// </summary>
/// <param name="slide">Slide pointer.</param>
/// <param name="width">Thumbnail width.</param>
/// <param name="height">Thumbnail height.</param>
/// <param name="thumb">Thumbnail JPEG data.</param>
/// <param name="thumbSize">Thumbnail size.</param>
/// <param name="colour">Whether to output pseudo-color image, 0 for grayscale, 1 for pseudo-color, default grayscale.</param>
/// <returns>Success or failure.</returns>
EXTERNC SQRAY_SLIDEBASE_EXPORT
bool sqrayslide_read_thumb_jpeg_by_channel(SlideImage* slide, int32_t* width, int32_t* height, unsigned char** thumb, int32_t* thumbSize, int32_t channel, int32_t colour = 0);

/// <summary>
/// Get specified single-channel image region in BGRA format.
/// </summary>
/// <param name="slide">Slide pointer.</param>
/// <param name="dest">Image region BGRA data.</param>
/// <param name="x">X-coordinate of region start point (pixel matrix, unit: pixels).</param>
/// <param name="y">Y-coordinate of region start point (pixel matrix, unit: pixels).</param>
/// <param name="w">Region width (pixel matrix, unit: pixels).</param>
/// <param name="h">Region height (pixel matrix, unit: pixels).</param>
/// <param name="level">Specified level.</param>
/// <param name="channel">Channel logical index.</param>
/// <param name="colour">Whether to output pseudo-color image, 0 for grayscale, 1 for pseudo-color, default grayscale.</param>
/// <returns>Success or failure.</returns>
EXTERNC SQRAY_SLIDEBASE_EXPORT
bool sqrayslide_read_region_bgra_by_channel(SlideImage* slide, unsigned char* dest, int32_t x, int32_t y, int32_t w, int32_t h, int32_t level, int32_t channel, int32_t colour = 0);

/// <summary>
/// Get specified single-channel tile in BGRA format.
/// </summary>
/// <param name="slide">Slide pointer.</param>
/// <param name="dest">Tile BGRA data.</param>
/// <param name="x">Tile X coordinate (tile matrix, unit: tiles).</param>
/// <param name="y">Tile Y coordinate (tile matrix, unit: tiles).</param>
/// <param name="level">Specified level.</param>
/// <param name="channel">Channel logical index.</param>
/// <param name="colour">Whether to output pseudo-color image, 0 for grayscale, 1 for pseudo-color, default grayscale.</param>
/// <returns>Success or failure.</returns>
EXTERNC SQRAY_SLIDEBASE_EXPORT
bool sqrayslide_read_tile_bgra_by_channel(SlideImage* slide, unsigned char* dest, int32_t x, int32_t y, int32_t level, int32_t channel, int32_t colour = 0);

/// <summary>
/// Get specified single-channel tile in JPEG format.
/// </summary>
/// <param name="slide">Slide pointer.</param>
/// <param name="dest">Tile JPEG data.</param>
/// <param name="x">Tile X coordinate (tile matrix, unit: tiles).</param>
/// <param name="y">Tile Y coordinate (tile matrix, unit: tiles).</param>
/// <param name="level">Specified level.</param>
/// <param name="channel">Channel logical index.</param>
/// <param name="colour">Whether to output pseudo-color image, 0 for grayscale, 1 for pseudo-color, default grayscale.</param>
/// <returns>Returns JPEG size on success, -1 on failure.</returns>
EXTERNC SQRAY_SLIDEBASE_EXPORT
int32_t sqrayslide_read_tile_jpeg_by_channel(SlideImage* slide, unsigned char** dest, int32_t x, int32_t y, int32_t level, int32_t channel, int32_t colour = 0);

/// <summary>
/// Get pseudo-color region BGRA after fusing specified channels.
/// </summary>
/// <param name="slide">Slide pointer.</param>
/// <param name="dest">Image region BGRA data.</param>
/// <param name="x">X-coordinate of region start point (pixel matrix, unit: pixels).</param>
/// <param name="y">Y-coordinate of region start point (pixel matrix, unit: pixels).</param>
/// <param name="w">Region width (pixel matrix, unit: pixels).</param>
/// <param name="h">Region height (pixel matrix, unit: pixels).</param>
/// <param name="level">Specified level.</param>
/// <param name="channels">Channel logical index list.</param>
/// <param name="cnelCount">Channel logical index list size.</param>
/// <returns>Success or failure.</returns>
EXTERNC SQRAY_SLIDEBASE_EXPORT
bool sqrayslide_read_region_bgra_by_channels(SlideImage* slide, unsigned char* dest, int32_t x, int32_t y, int32_t w, int32_t h, int32_t level, int32_t* channels, int32_t cnelCount);

/// <summary>
/// Get pseudo-color tile BGRA after fusing specified channels.
/// </summary>
/// <param name="slide">Slide pointer.</param>
/// <param name="dest">Tile BGRA data.</param>
/// <param name="x">Tile X coordinate (tile matrix, unit: tiles).</param>
/// <param name="y">Tile Y coordinate (tile matrix, unit: tiles).</param>
/// <param name="level">Specified level.</param>
/// <param name="channels">Channel logical index list.</param>
/// <param name="cnelCount">Channel logical index list size.</param>
/// <returns>Success or failure.</returns>
EXTERNC SQRAY_SLIDEBASE_EXPORT
bool sqrayslide_read_tile_bgra_by_channels(SlideImage* slide, unsigned char* dest, int32_t x, int32_t y, int32_t level, int32_t* channels, int32_t cnelCount);

/*****************************************************************************************************
 * ↑ Brightfield slides calling the above interfaces will all return failure,
 *   multi-channel interfaces all return pseudo-color images. ↑
 *****************************************************************************************************/
#pragma endregion

#pragma region Focal plane

/*
 * For multi-focal plane images, the focal plane index range is [0, count).
 * Index 0 represents the focal plane farthest from the slide surface.
 * As the index increases, the corresponding focal plane gradually gets closer to the slide surface.
 * Interfaces that don't specify a focal plane index default to reading image data from index count / 2.
 */

/// <summary>
/// Get the number of focal planes.
/// </summary>
/// <param name="slide">Slide pointer.</param>
/// <returns>Number of focal planes.</returns>
EXTERNC SQRAY_SLIDEBASE_EXPORT
int32_t sqrayslide_get_plane_count(SlideImage* slide);

/// <summary>
/// Get the physical distance between focal planes, in micrometers.
/// </summary>
/// <param name="slide">Slide pointer.</param>
/// <returns>Physical distance between focal planes.</returns>
EXTERNC SQRAY_SLIDEBASE_EXPORT
float sqrayslide_get_plane_space_between(SlideImage* slide);

/// <summary>
/// Get image region BGRA from specified focal plane. For fluorescence slides, outputs pseudo-color image fused from all channels.
/// </summary>
/// <param name="slide">Slide pointer.</param>
/// <param name="dest">Image region BGRA data.</param>
/// <param name="x">X-coordinate of region start point (pixel matrix, unit: pixels).</param>
/// <param name="y">Y-coordinate of region start point (pixel matrix, unit: pixels).</param>
/// <param name="w">Region width (pixel matrix, unit: pixels).</param>
/// <param name="h">Region height (pixel matrix, unit: pixels).</param>
/// <param name="level">Specified level.</param>
/// <param name="plane">Specified focal plane.</param>
/// <returns>Success or failure.</returns>
EXTERNC SQRAY_SLIDEBASE_EXPORT
bool sqrayslide_read_region_bgra_by_plane(SlideImage* slide, unsigned char* dest, int32_t x, int32_t y, int32_t w, int32_t h, int32_t level, int32_t plane);

/// <summary>
/// Get tile BGRA from specified focal plane. For fluorescence slides, outputs pseudo-color image fused from all channels.
/// </summary>
/// <param name="slide">Slide pointer.</param>
/// <param name="dest">Tile BGRA data.</param>
/// <param name="x">Tile X coordinate (tile matrix, unit: tiles).</param>
/// <param name="y">Tile Y coordinate (tile matrix, unit: tiles).</param>
/// <param name="level">Specified level.</param>
/// <param name="plane">Specified focal plane.</param>
/// <returns>Success or failure.</returns>
EXTERNC SQRAY_SLIDEBASE_EXPORT
bool sqrayslide_read_tile_bgra_by_plane(SlideImage* slide, unsigned char* dest, int32_t x, int32_t y, int32_t level, int32_t plane);

/// <summary>
/// Get tile JPEG from specified focal plane. Returns -1 on failure. For fluorescence slides, outputs pseudo-color image fused from all channels.
/// </summary>
/// <param name="slide">Slide pointer.</param>
/// <param name="dest">Tile JPEG data.</param>
/// <param name="x">Tile X coordinate (tile matrix, unit: tiles).</param>
/// <param name="y">Tile Y coordinate (tile matrix, unit: tiles).</param>
/// <param name="level">Specified level.</param>
/// <param name="plane">Specified focal plane.</param>
/// <returns>Returns JPEG size on success, -1 on failure.</returns>
EXTERNC SQRAY_SLIDEBASE_EXPORT
int32_t sqrayslide_read_tile_jpeg_by_plane(SlideImage* slide, unsigned char** dest, int32_t x, int32_t y, int32_t level, int32_t plane);

/// <summary>
/// Get the offset of specified focal plane relative to reference focal plane in X and Y directions.
/// </summary>
/// <param name="slide">Slide pointer.</param>
/// <param name="plane">Specified focal plane.</param>
/// <param name="level">Specified level.</param>
/// <param name="offsetX">Offset of specified focal plane relative to reference focal plane in X direction, in pixels.</param>
/// <param name="offsetY">Offset of specified focal plane relative to reference focal plane in Y direction, in pixels.</param>
/// <returns>Returns true on success, false on failure.</returns>
EXTERNC SQRAY_SLIDEBASE_EXPORT
bool sqrayslide_get_plane_offset(SlideImage* slide, int32_t plane, int32_t level, int32_t* offsetX, int32_t* offsetY);

#pragma endregion


/***************Interfaces defined in sqray_base header file********************************************************************


/*
 * Function: RGB color mapping table after CCM calibration
 * rgbRate: Input rgbRate ratio
 * hsvRate: Input hsvRate ratio
 * gamma: Input gamma value
 * redTable: Output red mapping table (externally allocated space) red[256][256][256]
 * greenTable: Output green mapping table (externally allocated space) green[256][256][256]
 * blueTable: Output blue mapping table (externally allocated space) blue[256][256][256]
 */
EXTERNC SQRAY_SLIDEBASE_EXPORT SqColorTable* InitColorCollectTable(float* rgbRate, float* hsvRate, float gamma, float* ccm);


/*
 * Function: Allocate space for RGB mapping table
 * return: Initialized color channel
 */
EXTERNC SQRAY_SLIDEBASE_EXPORT void DisposeColorCorrectTable(SqColorTable* ct);



/*
 * Function: Output BGRA colors after CCM calibration
 * srcBgra: Input BGRA data
 * dstBgra: Corrected BGRA data
 * width: Image width
 * height: Image height
 * colorTable: Color mapping table
 * parallel: Whether to process in parallel
 */
EXTERNC SQRAY_SLIDEBASE_EXPORT bool BgraColorCorrect(unsigned char* srcBgra, unsigned char* dstBgra, int width, int height, SqColorTable* colorTable, ColorStyle style, bool parallel = true);


/***************Interfaces defined in sqray_base header file********************************************************************/