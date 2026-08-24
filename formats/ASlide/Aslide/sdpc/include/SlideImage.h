#ifndef SLIDEIMAGE_H
#define SLIDEIMAGE_H
#include "sqray_base.h"
namespace SQRAYNS
{
	class SQRAY_SLIDEBASE_EXPORT SlideInfo
	{
	public:
		const char* ObjectName;
		const char* Suffixes;
		Int32 LevelCount;
		Int32 FocalPlaneCount;
		Float32 PlaneSpaceBetween;
		Float32 Rate;
		Float32 MppX;
		Float32 MppY;
		Float32 Scale;
		Float32 CcmGamma;
		Float32 CcmRgbRate[3];
		Float32 CcmHsvRate[3];
		Float32 Ccm[9];
		Int32 Channel = 4;
		SqSize TileSize;
		SqSize* ImageSize;
		SqSize* ImageSizeWithoutEdge;
		SqSize* TileCount;
		Float32* Downsample;
		SqSize* LeftTopEdge;
		SqSize* RightButtomEdge;
		SimpleImage* Thumbnail;
		SimpleImage* Macrograph;
		SimpleImage* Label;
		const char* Description;
		virtual ~SlideInfo();
	};

	class SQRAY_SLIDEBASE_EXPORT SlideImage : public SlideInfo
	{
	public:
		static unsigned char* BgraToJpeg(unsigned char* bgra, Int32& dstSize, const Int32& quality, const Int32& width, const Int32& height);
		SlideImage();
		int Quality = 75; // Quality used when compressing JPEG
		SqImageFormat ImageFormat;
		virtual int OpenImage() = 0;	// Open image
		virtual WSI_TYPE GetWSIType() = 0;	// Get slide type
		virtual Int32 GetChannelCount() = 0;	// Get channel count
		virtual bool IsSparse() = 0;	// Whether tiles are sparsely distributed (blocked)
		virtual Int32 GetBestLevelForDownsample(Float64 downsample);	// Get best level based on downsample factor
		virtual bool IsCorrected() = 0;	// Whether tiles in the file have been color corrected
		virtual const char* GetBarcode() = 0;	// Get barcode
		virtual unsigned char* GetSliceBgra(const Int32& level, const SqPoint& p, Int32* dataSize);
		virtual bool TryGetSliceBgra(unsigned char* bgra, const Int32& level, const SqPoint& p);
		virtual bool TryGetSliceBgraByPlane(unsigned char* bgra, const Int32& level, const SqPoint& p, const Int32& planeIndex);
		virtual void ColorCorrectBgra(unsigned char* bgra);
		virtual unsigned char* GetSliceJpeg(const Int32& level, const SqPoint& p, Int32* dataSize); // For efficiency, when tile format is JPEG and no color correction is needed, returns original JPEG data directly, Quality compression setting is invalid.
		virtual unsigned char* GetSliceJpegByPlane(const Int32& level, const SqPoint& p, Int32* dataSize, const Int32& planeIndex); // For efficiency, when tile format is JPEG and no color correction is needed, returns original JPEG data directly, Quality compression setting is invalid.
		virtual unsigned char* GetRegionBgra(const Int32& level, const SqRectangle& region, Int64* dataSize);
		virtual bool TryGetRegionBgra(unsigned char* bgra, const Int32& level, const SqRectangle& region);
		virtual bool TryGetRegionBgraByPlane(unsigned char* outBgra, const Int32& level, const SqRectangle& region, const Int32& planeIndex);
		virtual unsigned char* GetRegionJpeg(const Int32& level, const SqRectangle& region, Int32* dataSize);
		virtual unsigned char* GetSliceStream(const Int32& level, const SqPoint& p, Int32* dataSize) = 0;
		virtual Int32 GetLevelCount();
		virtual Int32 GetFocalPlaneCount();
		virtual Float32 GetPlaneSpaceBetween();
		virtual Int32 GetMiddlePlaneIndex();	// Get middle focal plane index, starting from 0
		virtual unsigned char* GetSliceStreamByPlane(const Int32& level, const SqPoint& p, Int32* dataSize, const Int32& planeIndex) = 0;
		virtual SqColorTable* GetInternalColorTableOrNull(); 	// Get built-in color table from slide parameters, returns null for fluorescence
		virtual void ApplyColorCorrection(bool apply, ColorStyle style = ColorStyle::Real);	// Whether to apply color correction based on slide built-in parameters, can be repeatedly applied or cancelled
		virtual void FreeArray(unsigned char*& array);
		virtual bool GetPlaneOffset(Int32& plane, Int32& level, Int32* offsetX, Int32* offsetY);
		~SlideImage() override;
	private:
		SlideImage(const SlideImage& obj) = delete;
		SlideImage(SlideImage&& obj) = delete;
		SlideImage& operator=(const SlideImage& obj) = delete;
		SlideImage& operator=(SlideImage&& obj) = delete;
		SqColorTable* _colorTable = nullptr; 	// Internal color mapping table of the slide, its lifecycle is controlled by SlideImage.
		ColorStyle _style;
		bool _appliedColorCorrection = false;
	};
}
#endif // !SLIDEIMAGE_H


