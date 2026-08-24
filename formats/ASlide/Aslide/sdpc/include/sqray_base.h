#pragma once
#ifndef SQRAYDSLIDEBASE_H
#define SQRAYDSLIDEBASE_H
#define SQRAYNS sqrayslide
#define SDPCNS sdpc
#define DCMNS dcm
#include <cstdlib>
#include <cstdio>
#include <cstdint>
#include <omp.h>
#ifdef _WIN32
#define WINDOWS
#include <setjmp.h>

#include <time.h>
#include <windows.h>
#include <io.h>
#include <string>
#define EXTERNC extern "C"


#define DLLEXPORT __declspec(dllexport)
#define DLLIMPORT __declspec(dllimport)
#elif defined __linux__
#define LINUX
//#include <sys/types.h>
//#include <sys/stat.h>
//#include <dirent.h>
//#include <unistd.h>

#define EXTERNC extern "C"
#define DLLEXPORT
#define DLLIMPORT
#define LINUX

#elif defined MACOS
#define EXTERNC extern "C"
#define DLLEXPORT
#define DLLIMPORT
//#define LINUX

#endif // WIN32 or __linux__
#define CPU_THREADS	omp_get_num_procs()	// Default CPU thread count
#define NUM_THREADS	CPU_THREADS	// Parallel thread count
#ifdef slidebase_EXPORTING
#define SQRAY_SLIDEBASE_EXPORT DLLEXPORT
#else
#define SQRAY_SLIDEBASE_EXPORT DLLEXPORT
#endif // slidebase_EXPORT
namespace SQRAYNS
{
	using Uint8 = std::uint8_t;
	using Int16 = std::int16_t;
	using Uint16 = std::uint16_t;
	using Int32 = std::int32_t;
	using Uint32 = std::uint32_t;
	using Int64 = std::int64_t;
	using Uint64 = std::uint64_t;
	using Float32 = float;
	using Float64 = double;

#pragma region Base type definition

	const int LutSize = 1 << 21;
	const int ColorRange = 256;
	const int ColorStep = 1;	//255/(52-1)

	enum class SQRAY_SLIDEBASE_EXPORT WSI_TYPE
	{
		Brightfield,
		Fluorescence
	};

	typedef enum _ColorStyle {
		Real = 0x01,
		Gorgeous
	}ColorStyle;

	typedef enum _ImageFormat
	{
		Jpeg = 0x00,
		Bmp,
		Png,
		Tiff,
		Hevc
	}SqImageFormat;

	typedef enum {
		JCS_UNKNOWN,            /* error/unspecified */
		JCS_GRAYSCALE,          /* monochrome */
		JCS_RGB,                /* red/green/blue as specified by the RGB_RED,
							 RGB_GREEN, RGB_BLUE, and RGB_PIXELSIZE macros */
		JCS_YCbCr,              /* Y/Cb/Cr (also known as YUV) */
		JCS_CMYK,               /* C/M/Y/K */
		JCS_YCCK,               /* Y/Cb/Cr/K */
		JCS_EXT_RGB,            /* red/green/blue */
		JCS_EXT_RGBX,           /* red/green/blue/x */
		JCS_EXT_BGR,            /* blue/green/red */
		JCS_EXT_BGRX,           /* blue/green/red/x */
		JCS_EXT_XBGR,           /* x/blue/green/red */
		JCS_EXT_XRGB,           /* x/red/green/blue */
		JCS_EXT_RGBA,           /* red/green/blue/alpha */
		JCS_EXT_BGRA,           /* blue/green/red/alpha */
		JCS_EXT_ABGR,           /* alpha/blue/green/red */
		JCS_EXT_ARGB,           /* alpha/red/green/blue */
		JCS_RGB565              /* 5-bit red/6-bit green/5-bit blue */
	}Sq_J_COLOR_SPACE;

	typedef struct SqRectangle
	{
		Int32 X;
		Int32 Y;
		Int32 Width;
		Int32 Height;
		explicit SqRectangle(Int32 x, Int32 y, Int32 width, Int32 height)
		{
			X = x;
			Y = y;
			Width = width;
			Height = height;
		}
	}SqRectangle;

	typedef struct _LutTable
	{
		unsigned char RedLutTable[LutSize];
		unsigned char GreenLutTable[LutSize];
		unsigned char BlueLutTable[LutSize];
	}LutTable;

	typedef struct SqColorTable
	{
		unsigned char* RedTable;
		unsigned char* GreenTable;
		unsigned char* BlueTable;
		unsigned char ColorRange[256];
		LutTable* GorgeousTable;
	}SqColorTable;

	struct SQRAY_SLIDEBASE_EXPORT SqSize
	{
		Int32 Width;
		Int32 Height;
		explicit SqSize(Int32 width = 0, Int32 height = 0) {
			Width = width;
			Height = height;
		}
	};

	struct SqPoint
	{
		Int32 X;
		Int32 Y;
		explicit SqPoint(Int32 x = 0, Int32 y = 0) {
			X = x;
			Y = y;
		}
	};

	struct  SimpleImage
	{
		unsigned char* Data = nullptr;
		Int32 Width;
		Int32 Height;
		Int32 DataSize;
		SqImageFormat Format;
		SimpleImage(unsigned char* data, Int32 dataSize, Int32 width, Int32 height, SqImageFormat format) {
			Data = data;
			DataSize = dataSize;
			Width = width;
			Height = height;
			Format = format;
		}
		~SimpleImage() 
		{
			if (Data != nullptr)
			{
				delete[] Data;
				Data = nullptr;
			}
		}
	};

	enum SqError
	{
		SqSuccess = 0x00,
		SqFileFormatError = -1,	// File format error
		SqOpenFileError = -2,	// File open error
		SqReadFileError = -3,	// File read error
		SqWriteFileError = -4,	// File write error
		SqJpegFormatError = -5,	// JPEG format error
		SqEncodeJpegError = -6,	// JPEG compression error
		SqDecodeJpegError = -7,	// JPEG decompression error
		SqSliceNumError = -8,	// Slice count error
		SqGetSliceRgbError = -9,	// RGB slice retrieval error
		SqPicInfoError = -10,	// Picture info error
		SqGetThumbnailError = -11,	// Thumbnail read error
		SqPicHeadError = -12,	// Header information error
		SqPathError = -13,	// Path error
		SqDataNullError = -14,	// Data is null
		SqPersonInfoError = -15, 	// Pathology information error
		SqMacrographInfoError = -16,	// Macro image information error
		SqNotExist = -17,	// Does not exist (if pathology info or macro image shows this, it's not an error and doesn't affect subsequent information)
		SqLayerIndexesError = -18,	// Level index error
		SqSliceIndexesError = -19, 	// Specified slice index error
		SqROIRange = -20,	// Value range error
		SqBlockJpeg = -21, 	// Custom SDPC block to JPEG error
		SqExtraInfoError = -22,	// Extra information error
		SqTileImageHeadError = -23,	// White blood cell information header error
		SqTileImageConfigCheckError = -24,	// Blood configuration file validation failed
		SqTileImageConfig2JsonError = -25,	// Blood configuration file to JSON conversion failed
		SqTileImageConfigNodeError = -26,	// Blood configuration file node retrieval failed
		SqTileImageConfigHeadError = -27,	// Blood configuration file header information error
		SqDecodeHevcError = -28,      	// HEVC decoding error
		SqDcmInstanceError = -29, 	// DICOM WSI single file information error
		SqDcmSeriesError = -30, 	// DICOM WSI series information error
		SqDcmZipParseError = -31, 	// DICOM WSI ZIP parsing error
		SqDcmZipInternalError = -32, 	// DICOM WSI ZIP internal error
	};
#pragma endregion

#pragma region Base method definition
	EXTERNC SQRAY_SLIDEBASE_EXPORT void SqFreeMemory(void* buf);

	EXTERNC SQRAY_SLIDEBASE_EXPORT void* SqMemset(void* dst, int val, Int64 size);
	EXTERNC SQRAY_SLIDEBASE_EXPORT int Access(const char* file, int mode);

	EXTERNC SQRAY_SLIDEBASE_EXPORT FILE* SqOpenFile(const char* path, const char* mode);

	EXTERNC SQRAY_SLIDEBASE_EXPORT void SqCloseFile(FILE* file);

	EXTERNC SQRAY_SLIDEBASE_EXPORT Int64 SqWriteFileData(FILE* file, void* data, Int64 size);

	/* Get the size of an opened file */
	EXTERNC SQRAY_SLIDEBASE_EXPORT Int64 SqGetFileSize(FILE* file);
	/* Get the size of a file at specified path */
	EXTERNC SQRAY_SLIDEBASE_EXPORT Int64 SqGetFileSizeSystemCall(char* path);

	EXTERNC SQRAY_SLIDEBASE_EXPORT unsigned char* SqReadFileData(FILE* file);

	EXTERNC SQRAY_SLIDEBASE_EXPORT Int64 SqReadData(void* data, Int64 elementSize, Int64 elementCount, FILE* file);

	EXTERNC SQRAY_SLIDEBASE_EXPORT Int64 SqWriteData(void* data, Int64 elementSize, Int64 elementCount, FILE* file);

	EXTERNC SQRAY_SLIDEBASE_EXPORT void SqRewind(FILE* file);

	EXTERNC SQRAY_SLIDEBASE_EXPORT int SqFseeki64(FILE* file, Int64 offset, int origin);

	EXTERNC SQRAY_SLIDEBASE_EXPORT Int64 SqFtelli64(FILE* file);

	/************************************************************************/
	/*
	 * Function: RGB color mapping table after CCM calibration
	 * rgbRate: Input rgbRate ratio
	 * hsvRate: Input hsvRate ratio
	 * gamma: Input gamma value
	 * redTable: Output red mapping table (externally allocated space) red[256][256][256]
	 * greenTable: Output green mapping table (externally allocated space) green[256][256][256]
	 * blueTable: Output blue mapping table (externally allocated space) blue[256][256][256]
	 */
	/************************************************************************/
	EXTERNC SQRAY_SLIDEBASE_EXPORT SqColorTable* InitColorCollectTable(float* rgbRate, float* hsvRate, float gamma, float* ccm);

	/************************************************************************/
	/*
	 * Function: Allocate space for RGB mapping table
	 * return: Initialized color channel
	 */
	/************************************************************************/
	EXTERNC SQRAY_SLIDEBASE_EXPORT void DisposeColorCorrectTable(SqColorTable* ct);

	/************************************************************************/
	/*
	 * Function: Output BGRA colors after CCM calibration
	 * srcBgra: Input BGRA data
	 * dstBgra: Corrected BGRA data
	 * width: Image width
	 * height: Image height
	 * colorTable: Color mapping table
	 * parallel: Whether to process in parallel
	 * return: Returns false on error, true on success
	 */
	/************************************************************************/
	EXTERNC SQRAY_SLIDEBASE_EXPORT bool BgraColorCorrect(unsigned char* srcBgra, unsigned char* dstBgra, int width, int height, SqColorTable* colorTable, ColorStyle style, bool parallel = true);
}
#pragma endregion
#endif // !SQRAYDCMBASE_H


