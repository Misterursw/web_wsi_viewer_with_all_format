/* Copyright (C) 2022, Intemedic. */

#pragma once

#include <stdarg.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>


/**
 * An archive error (e.g. IO error) occurred in the clip methods (e.g. read_region).
 */
#define TRON_CLIP_ARCHIVE_ERROR 100

/**
 * The argument to the clip methods (e.g. read_region) is invalid.
 */
#define TRON_CLIP_INVALID_ARGUMENT 101

/**
 * The supplied buffer does not have sufficient length to carry the string content.
 */
#define TRON_INSUFFICIENT_LENGTH 30

/**
 * The archive is invalid.
 */
#define TRON_INVALID_ARCHIVE 3

/**
 * The archive handler is invalid.
 */
#define TRON_INVALID_HANDLER 10

/**
 * The input image name was invalid.
 */
#define TRON_INVALID_IMAGE_NAME 40

/**
 * The specified LOD level is invalid.
 */
#define TRON_INVALID_LOD_LEVEL 20

/**
 * The input archive path was invalid.
 */
#define TRON_INVALID_PATH 1

/**
 * An IO error occurred while reading the archive.
 */
#define TRON_IO_ERROR 2

/**
 * The operation has completed successfully.
 */
#define TRON_SUCCESS 0

/**
 * An unknown error has occurred.
 */
#define TRON_UNKNOWN_ERROR -1

typedef struct Handle Handle;

/**
 * Represents the background color of a tron slide.
 */
typedef struct TronBackgroundColor {
  uint8_t red;
  uint8_t green;
  uint8_t blue;
} TronBackgroundColor;

/**
 * Represents the content region of a tron slide.
 */
typedef struct TronContentRegion {
  /**
   * Left coordinate of the content region.
   */
  int32_t left;
  /**
   * Top coordinate of the content region.
   */
  int32_t top;
  /**
   * Width of the content region.
   */
  int32_t width;
  /**
   * Height of the content region.
   */
  int32_t height;
} TronContentRegion;

/**
 * Represents the minimum and maximum LOD level of a tron slide.
 */
typedef struct TronLodLevelRange {
  /**
   * The minimum LOD level of the slide.
   */
  int32_t minimum;
  /**
   * The maximum LOD level of the slide.
   */
  int32_t maximum;
} TronLodLevelRange;

/**
 * Represents the dimensions of an image.
 */
typedef struct TronImageInfo {
  /**
   * Whether the requested image is existed.
   */
  bool existed;
  /**
   * Width of the image, in pixels.
   */
  size_t width;
  /**
   * Height of the image, in pixels.
   */
  size_t height;
  /**
   * Length of the image data, in bytes.
   */
  size_t length;
} TronImageInfo;

/**
 * Represents the resolution information of a tron slide.
 */
typedef struct TronResolution {
  /**
   * Resolution in the horizontal direction, in micrometers per pixel.
   * 0 if the resolution information is not provided.
   */
  float horizontal;
  /**
   * Resolution in the vertical direction, in micrometers per pixel
   * 0 if the resolution information is not provided.
   */
  float vertical;
} TronResolution;

/**
 * Represents the tile count information of a tron slide.
 */
typedef struct TronTileCount {
  /**
   * Tile count in the horizontal direction.
   */
  int32_t horizontal;
  /**
   * Tile count in the vertical direction.
   */
  int32_t vertical;
} TronTileCount;

/**
 * Represents the size of a tile.
 */
typedef struct TronTileSize {
  /**
   * Width of the tile.
   */
  int32_t width;
  /**
   * Height of the tile.
   */
  int32_t height;
} TronTileSize;

/**
 * Represents the version of a tron slide.
 */
typedef struct TronVersion {
  /**
   * The major version. 0 if the major version is not provided.
   */
  int32_t major;
  /**
   * The minor version. 0 if the minor version is not provided.
   */
  int32_t minor;
} TronVersion;

#ifdef __cplusplus
extern "C" {
#endif // __cplusplus

/**
 * Close a previously opened tron archive by its handle.
 *
 * Does not do anything if the specified `handle_ptr` is `nullptr`. Panics if the handle is not
 * a valid pointer created by `tron_open()`.
 */
void tron_close(struct Handle *handle_ptr);

/**
 * Gets the background color of the tron slide, which should be filled
 * in the blank areas.
 * Note if the archive did not specify a background color, white (0xffffff)
 * will be returned.
 *
 * Possible error codes:
 * - `TRON_INVALID_HANDLER`: the specified `handle_ptr` is not valid.
 */
struct TronBackgroundColor tron_get_background_color(struct Handle *handle_ptr);

/**
 * Gets the comments of the slide.
 *
 * Possible error codes:
 * - `TRON_INVALID_HANDLER`: the specified handler is not valid.
 * - `TRON_INSUFFICIENT_LENGTH`: the specified `size` is smaller than the content to retrieve.
 */
size_t tron_get_comments(struct Handle *handle_ptr, char *buffer_ptr, size_t size);

/**
 * Gets the content region, where the content area (i.e. non-blank area) resides
 * in the slide.
 *
 * Possible error codes:
 * - `TRON_INVALID_HANDLER`: the specified `handle_ptr` is not valid.
 */
struct TronContentRegion tron_get_content_region(struct Handle *handle_ptr);

/**
 * Gets the error code of last `tron_*()` call (other than `tron_get_last_error()` itself).
 *
 * If the call was successful, `TRON_SUCCESS` will be returned.
 */
int32_t tron_get_last_error(void);

/**
 * Gets the number of (Z-)layers in this archive.
 *
 * Possible error codes:
 * - `TRON_INVALID_HANDLER`: the specified handler is not valid.
 */
int32_t tron_get_layer_count(struct Handle *handle_ptr);

/**
 * Gets the scale ratios between the specified LOD level and its next level.
 *
 * Possible error codes:
 * - `TRON_INVALID_HANDLER`: the specified `handle_ptr` is not valid.
 * - `TRON_INVALID_LOD_LEVEL`: the specified `lod_level` is invalid, most likely out of range.
 * Returns 0f in this case.
 */
float tron_get_lod_gap_of(struct Handle *handle_ptr, size_t lod_level);

/**
 * Gets the LOD level range.
 *
 * Possible error codes:
 * - `TRON_INVALID_HANDLER`: the specified `handle_ptr` is not valid.
 */
struct TronLodLevelRange tron_get_lod_level_range(struct Handle *handle_ptr);

/**
 * Gets the maximum zoom level.
 *
 * Possible error codes:
 * - `TRON_INVALID_HANDLER`: the specified handler is not valid.
 */
float tron_get_maximum_zoom_level(struct Handle *handle_ptr);

/**
 * Gets the name of the slide.
 *
 * Possible error codes:
 * - `TRON_INVALID_HANDLER`: the specified handler is not valid.
 * - `TRON_INSUFFICIENT_LENGTH`: the specified `size` is smaller than the content to retrieve.
 */
size_t tron_get_name(struct Handle *handle_ptr, char *buffer_ptr, size_t size);

/**
 * Gets the pixel data of a named image.
 *
 * Possible error codes:
 * - `TRON_INVALID_HANDLER`: the specified handler is not valid.
 * - `TRON_INVALID_IMAGE_NAME`: the specified `image_name_ptr` does not point to a valid string.
 * - `TRON_UNKNOWN_ERROR`: an unknown error has occurred while retrieving image data.
 */
size_t tron_get_named_image_data(struct Handle *handle_ptr,
                                 const char *image_name_ptr,
                                 unsigned char *buffer_ptr);

/**
 * Gets the dimension information of a named image.
 *
 * Possible error codes:
 * - `TRON_INVALID_HANDLER`: the specified handler is not valid.
 * - `TRON_INVALID_IMAGE_NAME`: the specified `image_name_ptr` does not point to a valid string.
 * - `TRON_UNKNOWN_ERROR`: an unknown error has occurred while retrieving image data.
 */
struct TronImageInfo tron_get_named_image_info(struct Handle *handle_ptr,
                                               const char *image_name_ptr);

/**
 * Gets the quick hash of the slide, which can be utilized to identify a slide.
 *
 * Possible error codes:
 * - `TRON_INVALID_HANDLER`: the specified handler is not valid.
 * - `TRON_INSUFFICIENT_LENGTH`: the specified `size` is smaller than the content to retrieve.
 */
size_t tron_get_quick_hash(struct Handle *handle_ptr, char *buffer_ptr, size_t size);

/**
 * Gets the index of the representative (Z-)layer in this archive.
 * The representative layer is the layer which is meant to be rendered/analyzed by default.
 * Generally speaking, it's 1 for single-layered slide, or 0 for multi-layered slide for the
 * merged layer.
 *
 * Possible error codes:
 * - `TRON_INVALID_HANDLER`: the specified handler is not valid.
 */
int32_t tron_get_representative_layer_index(struct Handle *handle_ptr);

/**
 * Gets the resolution information.
 *
 * Possible error codes:
 * - `TRON_INVALID_HANDLER`: the specified `handle_ptr` is not valid.
 */
struct TronResolution tron_get_resolution(struct Handle *handle_ptr);

/**
 * Gets the tile count information.
 *
 * Possible error codes:
 * - `TRON_INVALID_HANDLER`: the specified `handle_ptr` is not valid.
 */
struct TronTileCount tron_get_tile_count(struct Handle *handle_ptr);

/**
 * Gets the pixel data of a tile image.
 *
 * Possible error codes:
 * - `TRON_INVALID_HANDLER`: the specified handler is not valid.
 * - `TRON_UNKNOWN_ERROR`: an unknown error has occurred while retrieving image data.
 */
size_t tron_get_tile_image_data(struct Handle *handle_ptr,
                                int32_t lod_level,
                                int32_t layer,
                                int32_t row,
                                int32_t column,
                                unsigned char *buffer_ptr);

/**
 * Gets the dimension information of a tile image.
 *
 * Possible error codes:
 * - `TRON_INVALID_HANDLER`: the specified handler is not valid.
 * - `TRON_UNKNOWN_ERROR`: an unknown error has occurred while retrieving image data.
 */
struct TronImageInfo tron_get_tile_image_info(struct Handle *handle_ptr,
                                              int32_t lod_level,
                                              int32_t layer,
                                              int32_t row,
                                              int32_t column);

/**
 * Gets the size of tiles in the archive, in pixels.
 *
 * Possible error codes:
 * - `TRON_INVALID_HANDLER`: the specified `handle_ptr` is not valid.
 */
struct TronTileSize tron_get_tile_size(struct Handle *handle_ptr);

/**
 * Gets the vendor name of the slide.
 *
 * Possible error codes:
 * - `TRON_INVALID_HANDLER`: the specified handler is not valid.
 * - `TRON_INSUFFICIENT_LENGTH`: the specified `size` is smaller than the content to retrieve.
 */
size_t tron_get_vendor(struct Handle *handle_ptr, char *ptr, size_t size);

/**
 * Gets the version of the tron archive.
 *
 * Possible error codes:
 * - `TRON_INVALID_HANDLER`: the specified `handle_ptr` is not valid.
 */
struct TronVersion tron_get_version(struct Handle *handle_ptr);

/**
 * Open a tron archive by its path.
 *
 * Possible error codes:
 * - `TRON_INVALID_PATH`: the specified `path_ptr` does not point to a valid string.
 * - `TRON_IO_ERROR`: an I/O error occurred while opening the specified file, such as file
 * not found, or insufficient privilege.
 * - `TRON_INVALID_ARCHIVE`: the specified file is not a valid tron archive.
 * - `TRON_UNKNOWN_ERROR`: an unknown error has occurred.
 */
struct Handle *tron_open(const char *path_ptr);

/**
 * Read image data in the specified region.
 *
 * Note: this function follows the parameter definition of openslide's read_region function.
 * x and y here are in the "world coordinate system", i.e. reference to LOD0. However, width
 * and height is in the target lod_level's coordinate system.
 * Unlike openslide, this method outputs BGR24 pixels (rather than BGRA32 pixels). The input
 * buffer must have a length of at least width * heigth * 3 bytes.
 *
 * Possible error codes:
 * - `TRON_CLIP_ARCHIVE_ERROR`: an archive error (e.g. IO error) occurred.
 * - `TRON_CLIP_INVALID_ARGUMENT`: one or more input argument is invalid.
 */
size_t tron_read_region(struct Handle *handle_ptr,
                        int32_t lod_level,
                        int32_t layer,
                        int32_t x,
                        int32_t y,
                        size_t width,
                        size_t height,
                        unsigned char *buffer_ptr);

#ifdef __cplusplus
} // extern "C"
#endif // __cplusplus
