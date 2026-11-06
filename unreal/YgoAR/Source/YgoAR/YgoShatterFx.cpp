#include "YgoShatterFx.h"

#include "Components/InstancedStaticMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/Texture2D.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "UObject/ConstructorHelpers.h"
#include "YgoEase.h"
#include "YgoFeel.h"
#include "YgoParticles.h"
#include "YgoTableView.h"

namespace
{
	const FLinearColor Fire = FLinearColor::FromSRGBColor(FColor(255, 150, 60));  // web/duel.js RGB.fire
}

AYgoShatterFx::AYgoShatterFx()
{
	PrimaryActorTick.bCanEverTick = true;
	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Plane(TEXT("/Engine/BasicShapes/Plane.Plane"));
	Shards = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("Shards"));
	Shards->SetupAttachment(GetRootComponent());
	Shards->SetStaticMesh(Plane.Object);
	Shards->NumCustomDataFloats = 4;  // the cell (Q, R), Alpha, Hot
	Shards->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Shards->CastShadow = false;
	Shards->TranslucencySortPriority = 5;
	Glow = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Glow"));
	Glow->SetupAttachment(GetRootComponent());
	Glow->SetStaticMesh(Plane.Object);
	Glow->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Glow->CastShadow = false;
	Glow->TranslucencySortPriority = 4;
}

double AYgoShatterFx::Clock() const
{
	UYgoFeel* Feel = UYgoFeel::Get(this);
	return Feel ? Feel->Seconds() : FPlatformTime::Seconds();
}

void AYgoShatterFx::Start(const FTransform& InFigure, const FVector2D& SizeCm, float CardWidthCm, UTexture2D* Sprite,
	AYgoTableView* View, UYgoParticles* Particles)
{
	Figure = InFigure; Size = SizeCm; Width = CardWidthCm;
	StartedAt = Clock();
	if (UMaterialInterface* M = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/YgoAR/M_FxShard.M_FxShard")))
	{
		UMaterialInstanceDynamic* D = UMaterialInstanceDynamic::Create(M, this);
		D->SetTextureParameterValue(TEXT("Sprite"), Sprite);
		Shards->SetMaterial(0, D);
	}
	if (UMaterialInterface* M = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/YgoAR/M_FxMagic.M_FxMagic")))
	{
		GlowFx = UMaterialInstanceDynamic::Create(M, this);
		GlowFx->SetScalarParameterValue(TEXT("Mode"), 6.f);
		GlowFx->SetVectorParameterValue(TEXT("Color"), Fire);
		Glow->SetMaterial(0, GlowFx);
	}
	TArray<FTransform> Pieces;
	Pieces.Init(Figure, Cells * Cells);
	Shards->AddInstances(Pieces, false, true);
	Glow->SetWorldTransform(FTransform(Figure.GetRotation(), Figure.GetLocation(), FVector(1.2f * Width * 2 / 100.f)));

	if (UYgoFeel* Feel = UYgoFeel::Get(this)) { Feel->Blow(EYgoWeight::Light); Feel->Play(EYgoSound::Shatter); }
	const FVector Right = Figure.GetUnitAxis(EAxis::X), Down = Figure.GetUnitAxis(EAxis::Y);
	for (int32 i = 0; Particles && i < 40; ++i)
	{
		// Embers rising from where the figure stood.
		FYgoParticle E;
		E.Position = Figure.GetLocation() + Right * FMath::FRandRange(-.5f, .5f) * Size.X + Down * FMath::FRandRange(-.5f, .5f) * Size.Y;
		E.Velocity = -Down * Width * (.3f + .9f * FMath::FRand()) + Right * FMath::FRandRange(-.25f, .25f) * Width;
		E.Color = Fire * 3.f; E.Size = Width * .03f; E.Life = 1.f + 1.f * FMath::FRand(); E.Delay = .1f * FMath::FRand();
		Particles->Emit(E);
	}
	Tick(0.f);
}

void AYgoShatterFx::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	const float T = (Clock() - StartedAt) / Duration;
	if (T >= 1.f) { Destroy(); return; }
	using namespace YgoEase;
	const float K = Out(T), Burn = Span(T, .1f, .9f), Hot = (1 - Burn) * .6f * Span(T, 0, .25f);
	const FQuat Base = Figure.GetRotation();
	for (int32 R = 0; R < Cells; ++R)
		for (int32 Q = 0; Q < Cells; ++Q)
		{
			// As the 2D pieces: each column flies out sideways, each piece lifts a little and then falls
			// (down the figure, as gravity on screen), spinning; some come at the camera, some go back.
			const float S = ((R * 7 + Q * 13) % 10) / 10.f;
			const float X = (Q - (Cells - 1) / 2.f) / Cells * Size.X * (1 + .8f * K * (.7f + .6f * S));
			const float Up = ((Cells - 1) / 2.f - R) / Cells * Size.Y + Width * .4f * K * (1 - S) - Width * 2.2f * T * T;
			const float Z = Width * .3f * K * (S - .5f);
			const FQuat Spin = Base * FQuat(FVector::ZAxisVector, (Q - R + S) * 1.4f * K);
			const int32 i = R * Cells + Q;
			Shards->UpdateInstanceTransform(i, FTransform(Spin, Figure.TransformPosition(FVector(X, -Up, Z)), FVector(Size.X / Cells / 100.f, Size.Y / Cells / 100.f, 1)), true, false, true);
			const float Data[4] = {float(Q), float(R), 1 - Burn, Hot};
			Shards->SetCustomData(i, TArrayView<const float>(Data, 4), false);
		}
	Shards->MarkRenderStateDirty();
	if (GlowFx) GlowFx->SetScalarParameterValue(TEXT("Alpha"), .5f * (1 - Span(T, 0, .4f)));
}
