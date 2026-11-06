#include "YgoSummonFx.h"

#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "UObject/ConstructorHelpers.h"
#include "YgoEase.h"
#include "YgoFeel.h"
#include "YgoParticles.h"
#include "YgoTableView.h"

AYgoSummonFx::AYgoSummonFx()
{
	PrimaryActorTick.bCanEverTick = true;
	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Plane(TEXT("/Engine/BasicShapes/Plane.Plane"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Cylinder(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	auto Make = [this](const TCHAR* Name, UStaticMesh* Mesh)
	{
		UStaticMeshComponent* C = CreateDefaultSubobject<UStaticMeshComponent>(Name);
		C->SetupAttachment(GetRootComponent());
		C->SetStaticMesh(Mesh);
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->CastShadow = false;
		return C;
	};
	Circle = Make(TEXT("Circle"), Plane.Object);
	Shock = Make(TEXT("Shock"), Plane.Object);
	Pillar = Make(TEXT("Pillar"), Cylinder.Object);
	Circle->TranslucencySortPriority = 1; Shock->TranslucencySortPriority = 2; Pillar->TranslucencySortPriority = 4;
}

double AYgoSummonFx::Clock() const
{
	UYgoFeel* Feel = UYgoFeel::Get(this);
	return Feel ? Feel->Seconds() : FPlatformTime::Seconds();
}

UMaterialInstanceDynamic* AYgoSummonFx::Fx(UStaticMeshComponent* Mesh, const TCHAR* Material)
{
	UMaterialInterface* M = LoadObject<UMaterialInterface>(nullptr, Material);
	if (!M) return nullptr;
	UMaterialInstanceDynamic* D = UMaterialInstanceDynamic::Create(M, this);
	Mesh->SetMaterial(0, D);
	return D;
}

void AYgoSummonFx::Start(const FVector& Where, float CardWidthCm, const FLinearColor& InColor, AYgoTableView* InView, UYgoParticles* InParticles)
{
	SetActorLocation(Where);
	Width = CardWidthCm; Color = InColor; View = InView; Particles = InParticles;
	Seed = FMath::FRand() * 10.f;
	StartedAt = Clock();
	if (UYgoFeel* Feel = UYgoFeel::Get(this)) Feel->Play(EYgoSound::Rise);
	CircleFx = Fx(Circle, TEXT("/Game/YgoAR/M_FxMagic.M_FxMagic"));
	ShockFx = Fx(Shock, TEXT("/Game/YgoAR/M_FxMagic.M_FxMagic"));
	PillarFx = Fx(Pillar, TEXT("/Game/YgoAR/M_FxBeam.M_FxBeam"));
	for (UMaterialInstanceDynamic* D : {CircleFx.Get(), ShockFx.Get(), PillarFx.Get()})
		if (D) { D->SetVectorParameterValue(TEXT("Color"), Color); D->SetScalarParameterValue(TEXT("Seed"), Seed); }
	if (CircleFx) CircleFx->SetScalarParameterValue(TEXT("Mode"), 0.f);
	if (ShockFx) ShockFx->SetScalarParameterValue(TEXT("Mode"), 2.f);
	Circle->SetRelativeLocation(FVector(0, 0, .05f));
	Shock->SetRelativeLocation(FVector(0, 0, .08f));
	Tick(0.f);
}

void AYgoSummonFx::Impact()
{
	bFired = true;
	if (UYgoFeel* Feel = UYgoFeel::Get(this))
	{
		Feel->Blow(EYgoWeight::Medium);
		Feel->Play(EYgoSound::Burst);
		Feel->Play(EYgoSound::Boom, .6f);
	}
	UYgoParticles* P = Particles.Get();
	if (!P) return;
	const FVector Centre = GetActorLocation();
	// Sparks flying out over the table, hot and stretched along their path.
	for (int32 i = 0; i < 48; ++i)
	{
		const float A = FMath::FRand() * 2 * PI, Speed = Width * (1.f + 2.2f * FMath::FRand());
		FYgoParticle S;
		S.Position = Centre + FVector(FMath::Cos(A), FMath::Sin(A), 0) * Width * .2f + FVector(0, 0, .3f);
		S.Velocity = FVector(FMath::Cos(A) * Speed, FMath::Sin(A) * Speed, Width * (.4f + 1.2f * FMath::FRand()));
		S.Color = (FMath::FRand() < .3f ? FLinearColor::White : Color) * 6.f;
		S.Size = Width * .035f; S.Life = .45f + .45f * FMath::FRand();
		S.Gravity = Width * 5.f; S.Drag = 1.8f; S.Stretch = .045f;
		P->Emit(S);
	}
	// Motes rising from the circle, slow and soft.
	for (int32 i = 0; i < 40; ++i)
	{
		const float A = FMath::FRand() * 2 * PI, R = Width * 1.3f * (.3f + .7f * FMath::FRand());
		FYgoParticle M;
		M.Position = Centre + FVector(FMath::Cos(A) * R, FMath::Sin(A) * R, .2f);
		M.Velocity = FVector(FMath::Cos(A), FMath::Sin(A), 0) * Width * .15f + FVector(0, 0, Width * (.6f + 1.4f * FMath::FRand()));
		M.Color = FMath::Lerp(Color, FLinearColor::White, .35f * FMath::FRand()) * 3.f;
		M.Size = Width * (.03f + .035f * FMath::FRand()); M.Life = .9f + .8f * FMath::FRand();
		M.Drag = .6f; M.Delay = .15f * FMath::FRand();
		P->Emit(M);
	}
}

void AYgoSummonFx::Tick(float Dt)
{
	Super::Tick(Dt);
	const float T = (Clock() - StartedAt) / Duration;
	if (T >= 1.f) { Destroy(); return; }
	using namespace YgoEase;
	const float S = T;  // the 2D version's beats (fractions of its 1.3 s), stretched to Duration
	if (!bFired && S > .3f) Impact();

	// Magic circle: opens fast, turns, fades in the last 30 %.
	const float Open = Out(Span(S, 0, .35f));
	Circle->SetRelativeScale3D(FVector(Width * 1.8f * (.3f + .9f * Open) / 100.f));  // up to 2.2 card widths across
	if (CircleFx)
	{
		CircleFx->SetScalarParameterValue(TEXT("Progress"), S);
		CircleFx->SetScalarParameterValue(TEXT("Alpha"), .95f * (1 - Span(S, .7f, 1)));
	}
	// Shockwave: grows to 2 card widths across between 30 % and 75 %.
	const float W = Span(S, .3f, .75f);
	Shock->SetVisibility(W > 0 && W < 1);
	Shock->SetRelativeScale3D(FVector(Width * .88f * (.3f + 2.f * Out(W)) / 100.f));
	if (ShockFx)
	{
		ShockFx->SetScalarParameterValue(TEXT("Progress"), W);
		ShockFx->SetScalarParameterValue(TEXT("Alpha"), FMath::Square(1 - W));
	}
	// Pillar of light: rises from 12 % to 40 %, fades from 55 %.
	const float Up = Out(Span(S, .12f, .4f)), Down = 1 - Span(S, .55f, 1);
	const float Height = FMath::Max(.01f, Width * 3.2f * Up);
	Pillar->SetVisibility(Up > 0 && Down > 0);
	Pillar->SetRelativeScale3D(FVector(Width * 1.1f / 100.f, Width * 1.1f / 100.f, Height / 100.f));
	Pillar->SetRelativeLocation(FVector(0, 0, Height / 2));
	if (PillarFx)
	{
		PillarFx->SetScalarParameterValue(TEXT("Alpha"), .9f * Down);
		PillarFx->SetScalarParameterValue(TEXT("Progress"), S);
	}
}
