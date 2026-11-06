// The HUD's plate (M_UiPlate): lapis lacquer in a gold rim, one widget for the life point cartouches,
// the phase tiles and the buttons, so they read as one object. The material works in half-heights of
// the widget, so Tick hands it the widget's own shape; sizes here are in Slate units.
#pragma once

#include "CoreMinimal.h"
#include "Styling/SlateBrush.h"
#include "UObject/StrongObjectPtr.h"
#include "Widgets/SCompoundWidget.h"

class UMaterialInstanceDynamic;

namespace YgoPlate
{
	inline const FLinearColor Lapis(.008f, .025f, .11f);
	inline const FLinearColor Gold(.80f, .55f, .20f);
}

class SYgoPlate : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SYgoPlate)
		: _Radius(12.f), _Rim(4.f), _Knot(0.f), _Body(.92f), _Padding(FMargin(0))
		, _Fill(YgoPlate::Lapis), _Accent(YgoPlate::Gold), _Lit(0.f), _Sheen(0.f), _Alpha(1.f)
	{}
		SLATE_ARGUMENT(float, Radius)
		SLATE_ARGUMENT(float, Rim)
		SLATE_ARGUMENT(float, Knot)    // +1 ties it off on the right, -1 on the left: a cartouche
		SLATE_ARGUMENT(float, Body)    // the lacquer's opacity
		SLATE_ARGUMENT(FMargin, Padding)
		SLATE_ATTRIBUTE(FLinearColor, Fill)
		SLATE_ATTRIBUTE(FLinearColor, Accent)
		SLATE_ATTRIBUTE(float, Lit)    // 0 to 1: warms it
		SLATE_ATTRIBUTE(float, Sheen)  // 0 to 1: one glint across it
		SLATE_ATTRIBUTE(float, Alpha)
		SLATE_DEFAULT_SLOT(FArguments, Content)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);
	virtual void Tick(const FGeometry& Geometry, const double CurrentTime, const float DeltaTime) override;

private:
	TStrongObjectPtr<UMaterialInstanceDynamic> Material;
	FSlateBrush Brush;
	float Radius = 12.f, Rim = 4.f;
	TAttribute<FLinearColor> Fill, Accent;
	TAttribute<float> Lit, Sheen, Alpha;
	FVector2f Shape = FVector2f::ZeroVector;
};
