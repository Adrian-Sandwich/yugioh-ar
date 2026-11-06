#include "YgoFx.h"

#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "UObject/ConstructorHelpers.h"
#include "YgoEase.h"
#include "YgoFeel.h"
#include "YgoHud.h"
#include "YgoParticles.h"
#include "YgoTableView.h"

namespace
{
	constexpr float OnPlane = .44f;  // card widths in one of the 2D view's plane units
	constexpr float Bigger = 1.4f;   // the 3D view draws an activation's circle this much larger

	void Param(UMaterialInstanceDynamic* M, const TCHAR* Name, float Value) { if (M) M->SetScalarParameterValue(Name, Value); }
}

AYgoFx::AYgoFx()
{
	PrimaryActorTick.bCanEverTick = true;
	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Plane(TEXT("/Engine/BasicShapes/Plane.Plane"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Cylinder(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	Glow = Make(TEXT("Glow"), Plane.Object, 1);
	Disc = Make(TEXT("Disc"), Plane.Object, 2);
	Beam = Make(TEXT("Beam"), Cylinder.Object, 4);
}

UStaticMeshComponent* AYgoFx::Make(const TCHAR* Name, UStaticMesh* Mesh, int32 SortPriority)
{
	UStaticMeshComponent* C = CreateDefaultSubobject<UStaticMeshComponent>(Name);
	C->SetupAttachment(GetRootComponent());
	C->SetStaticMesh(Mesh);
	C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	C->CastShadow = false;
	C->TranslucencySortPriority = SortPriority;
	return C;
}

double AYgoFx::Clock() const
{
	UYgoFeel* Feel = UYgoFeel::Get(this);
	return Feel ? Feel->Seconds() : FPlatformTime::Seconds();
}

float AYgoFx::Duration(EYgoFx Kind)
{
	switch (Kind)
	{
	case EYgoFx::Spell: return 2.1f;   // 2D: 1.4 s
	case EYgoFx::Trap: return 1.5f;    // 1.0 s
	case EYgoFx::Set: return 1.35f;    // 0.9 s
	default: return 1.f;               // impact: 0.65 s
	}
}

void AYgoFx::Lay(UStaticMeshComponent* Plane, float Radius, float Height)
{
	// The engine's plane: 100 x 100 cm, facing up.
	Plane->SetRelativeScale3D(FVector(FMath::Max(Radius, .01f) * 2 / 100.f));
	Plane->SetRelativeLocation(FVector(0, 0, Height));
}

void AYgoFx::Start(EYgoFx InKind, const FVector& Where, float CardWidthCm, const FLinearColor& InColor,
	AYgoTableView* InView, UYgoParticles* InParticles, TSharedPtr<SYgoHud> InHud)
{
	Kind = InKind; Width = CardWidthCm; Color = InColor; View = InView; Particles = InParticles; Hud = InHud;
	SetActorLocation(Where);
	Seed = FMath::FRand() * 10.f;
	StartedAt = Clock();
	auto Fx = [this](UStaticMeshComponent* Mesh, const TCHAR* Material) -> UMaterialInstanceDynamic*
	{
		UMaterialInterface* M = LoadObject<UMaterialInterface>(nullptr, Material);
		if (!M) return nullptr;
		UMaterialInstanceDynamic* D = UMaterialInstanceDynamic::Create(M, this);
		D->SetVectorParameterValue(TEXT("Color"), Color);
		D->SetScalarParameterValue(TEXT("Seed"), Seed);
		Mesh->SetMaterial(0, D);
		return D;
	};
	DiscFx = Fx(Disc, TEXT("/Game/YgoAR/M_FxMagic.M_FxMagic"));
	GlowFx = Fx(Glow, TEXT("/Game/YgoAR/M_FxMagic.M_FxMagic"));
	BeamFx = Fx(Beam, TEXT("/Game/YgoAR/M_FxBeam.M_FxBeam"));
	const float Mode = Kind == EYgoFx::Spell ? 0.f : Kind == EYgoFx::Trap ? 3.f : Kind == EYgoFx::Set ? 5.f : 2.f;
	Param(DiscFx, TEXT("Mode"), Mode);
	Param(DiscFx, TEXT("Span"), Kind == EYgoFx::Trap ? 2.6f : 1.5f);  // the plane's half-size in plane units (Tick)
	Param(GlowFx, TEXT("Mode"), 6.f);
	Beam->SetVisibility(false);
	Tick(0.f);
}

void AYgoFx::Fire()
{
	bFired = true;
	UYgoFeel* Feel = UYgoFeel::Get(this);
	UYgoParticles* P = Particles.Get();
	const FVector Centre = GetActorLocation();
	const float U = OnPlane * Width;
	auto Around = [&](float Radius) { const float A = FMath::FRand() * 2 * PI; return FVector(FMath::Cos(A), FMath::Sin(A), 0) * Radius; };
	switch (Kind)
	{
	case EYgoFx::Spell:
		if (Feel) { Feel->Play(EYgoSound::Spell); Feel->Play(EYgoSound::Rise, .7f); }
		// Glyphs drifting up from the circle.
		for (int32 i = 0; P && i < 30; ++i)
		{
			FYgoParticle M;
			M.Position = Centre + Around(U * Bigger * 1.1f * FMath::Sqrt(FMath::FRand())) + FVector(0, 0, .3f);
			M.Velocity = FVector(FMath::FRandRange(-.1f, .1f) * Width, FMath::FRandRange(-.1f, .1f) * Width, Width * (.5f + FMath::FRand()));
			M.Color = Color * 2.5f; M.Size = Width * .035f; M.Life = 1.4f + .9f * FMath::FRand();
			M.Drag = .3f; M.Delay = .3f * FMath::FRand();
			P->Emit(M);
		}
		break;
	case EYgoFx::Trap:
		if (Feel) { Feel->Blow(EYgoWeight::Medium); Feel->Play(EYgoSound::Trap); Feel->Play(EYgoSound::Boom, .5f); }
		if (Hud.IsValid() && !(Feel && Feel->IsCalm())) Hud->Flash(Color, .12f, .33f);
		for (int32 i = 0; P && i < 36; ++i)
		{
			const FVector Dir = Around(1.f);
			FYgoParticle S;
			S.Position = Centre + Dir * Width * .2f + FVector(0, 0, .3f);
			S.Velocity = Dir * Width * (1.2f + 2.f * FMath::FRand()) + FVector(0, 0, Width * (.3f + .6f * FMath::FRand()));
			S.Color = (FMath::FRand() < .3f ? FLinearColor::White : Color) * 5.f;
			S.Size = Width * .03f; S.Life = .45f + .35f * FMath::FRand();
			S.Gravity = Width * 4.f; S.Drag = 2.f; S.Stretch = .04f;
			P->Emit(S);
		}
		break;
	case EYgoFx::Set:
		if (Feel) { Feel->Blow(EYgoWeight::Light); Feel->Play(EYgoSound::Set); Feel->Play(EYgoSound::Card, .7f); }
		// The back's light gathers into the zone from all around.
		for (int32 i = 0; P && i < 26; ++i)
		{
			FYgoParticle M;
			const FVector From = Around(1.6f * U * 1.2f);
			M.Position = Centre + From + FVector(0, 0, .3f);
			M.Life = .65f * 1.5f;
			M.Velocity = -From / M.Life;
			M.Color = Color * 2.5f; M.Size = Width * .03f;
			P->Emit(M);
		}
		break;
	case EYgoFx::Impact:
	{
		const float S = 1.6f * Width;
		if (Feel) { Feel->Blow(EYgoWeight::Heavy); Feel->Play(EYgoSound::Hit); Feel->Play(EYgoSound::Boom, .8f); }
		if (Hud.IsValid() && !(Feel && Feel->IsCalm())) Hud->Flash(FLinearColor::White, .18f, .24f);
		for (int32 i = 0; P && i < 46; ++i)
		{
			const FVector Dir = Around(1.f);
			FYgoParticle K;
			K.Position = Centre + FVector(0, 0, .5f);
			K.Velocity = Dir * S * (2.f + 4.5f * FMath::FRand()) + FVector(0, 0, S * (.5f + FMath::FRand()));
			K.Color = (FMath::FRand() < .5f ? FLinearColor::White : Color) * 6.f;
			K.Size = S * .033f; K.Life = .45f + .45f * FMath::FRand();
			K.Gravity = S * 6.f; K.Drag = 5.f; K.Stretch = .03f;
			P->Emit(K);
		}
		for (int32 i = 0; P && i < 16; ++i)
		{
			FYgoParticle Puff;
			Puff.Position = Centre + FVector(0, 0, .5f);
			Puff.Velocity = Around(S * .5f) + FVector(0, 0, S * .3f);
			Puff.Color = Color * 1.2f; Puff.Size = S * .12f; Puff.Life = 1.f; Puff.Drag = 1.f;
			P->Emit(Puff);
		}
		break;
	}
	}
}

void AYgoFx::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	const float T = (Clock() - StartedAt) / Duration(Kind);
	if (T >= 1.f) { Destroy(); return; }
	if (!bFired) Fire();
	using namespace YgoEase;
	const float U = OnPlane * Width;
	switch (Kind)
	{
	case EYgoFx::Spell:
	{
		// Mode 0 draws its outer ring at 0.95 of the plane.
		Lay(Disc, (.4f + 1.1f * Back(Span(T, 0, .45f))) * U * Bigger / .95f, .05f);
		Param(DiscFx, TEXT("Progress"), Span(T, 0, .45f));
		Param(DiscFx, TEXT("Alpha"), 1 - Span(T, .7f, 1));
		Lay(Glow, 1.2f * Width, .03f);
		Param(GlowFx, TEXT("Alpha"), .35f * (1 - Span(T, .5f, 1)));
		const float Rise = Out(Span(T, .1f, .45f)), Height = FMath::Max(.01f, 2.4f * Width * Rise);
		Beam->SetVisibility(Rise > 0);
		Beam->SetRelativeScale3D(FVector(.8f * Width / 100.f, .8f * Width / 100.f, Height / 100.f));
		Beam->SetRelativeLocation(FVector(0, 0, Height / 2));
		Param(BeamFx, TEXT("Alpha"), .6f * (1 - Span(T, .5f, 1)));
		break;
	}
	case EYgoFx::Trap:
		Lay(Disc, 2.6f * U * 1.3f, .05f);  // chains reach 2.5 plane units
		Param(DiscFx, TEXT("Progress"), T);
		Param(DiscFx, TEXT("Alpha"), 1 - Span(T, .6f, 1));
		Lay(Glow, Width * (.5f + 1.2f * Out(Span(T, 0, .3f))), .03f);
		Param(GlowFx, TEXT("Alpha"), .55f * (1 - Span(T, .2f, .8f)));
		break;
	case EYgoFx::Set:
		Lay(Disc, 1.5f * U * 1.2f, .05f);
		Param(DiscFx, TEXT("Progress"), T);
		Param(DiscFx, TEXT("Alpha"), (1 - T) * .8f);
		Lay(Glow, .8f * Width, .03f);
		Param(GlowFx, TEXT("Alpha"), .4f * Span(T, .5f, .8f) * (1 - Span(T, .8f, 1)));
		break;
	case EYgoFx::Impact:
	{
		const float S = 1.6f * Width;
		Lay(Glow, S * (.4f + 1.1f * Out(T)), .1f);
		Param(GlowFx, TEXT("Alpha"), .9f * (1 - T));
		Lay(Disc, S * Out(T) / .85f, .08f);  // Mode 2's ring is at 0.85 of the plane, and as thick as it is wide
		Param(DiscFx, TEXT("Alpha"), .8f * FMath::Square(1 - T));
		break;
	}
	}
}
