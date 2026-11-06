#include "YgoPlate.h"

#include "Materials/MaterialInstanceDynamic.h"
#include "UObject/Package.h"
#include "Widgets/Layout/SBorder.h"

void SYgoPlate::Construct(const FArguments& InArgs)
{
	Radius = InArgs._Radius; Rim = InArgs._Rim;
	Fill = InArgs._Fill; Accent = InArgs._Accent; Lit = InArgs._Lit; Sheen = InArgs._Sheen; Alpha = InArgs._Alpha;
	if (UMaterialInterface* M = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/YgoAR/M_UiPlate.M_UiPlate")))
	{
		Material.Reset(UMaterialInstanceDynamic::Create(M, GetTransientPackage()));
		Material->SetScalarParameterValue(TEXT("Knot"), InArgs._Knot);
		Material->SetScalarParameterValue(TEXT("Body"), InArgs._Body);
		Brush.SetResourceObject(Material.Get());
		Brush.DrawAs = ESlateBrushDrawType::Image;
		Brush.ImageSize = FVector2D(64, 64);
	}
	ChildSlot
	[
		SNew(SBorder)
		.BorderImage(&Brush)
		.Padding(InArgs._Padding)
		[
			InArgs._Content.Widget
		]
	];
}

void SYgoPlate::Tick(const FGeometry& Geometry, const double CurrentTime, const float DeltaTime)
{
	SCompoundWidget::Tick(Geometry, CurrentTime, DeltaTime);
	if (!Material.IsValid()) return;
	const FVector2f Size = FVector2f(Geometry.GetLocalSize());
	if (Size.Y > 1 && !Size.Equals(Shape, .5f))
	{
		Shape = Size;
		const float HalfHeight = Size.Y / 2;
		Material->SetScalarParameterValue(TEXT("Aspect"), Size.X / Size.Y);
		Material->SetScalarParameterValue(TEXT("Radius"), FMath::Min(Radius / HalfHeight, 1.f));
		Material->SetScalarParameterValue(TEXT("Rim"), Rim / HalfHeight);
	}
	Material->SetVectorParameterValue(TEXT("Fill"), Fill.Get());
	Material->SetVectorParameterValue(TEXT("Accent"), Accent.Get());
	Material->SetScalarParameterValue(TEXT("Lit"), Lit.Get());
	Material->SetScalarParameterValue(TEXT("Sheen"), Sheen.Get());
	Material->SetScalarParameterValue(TEXT("Alpha"), Alpha.Get());
}
