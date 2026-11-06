#include "YgoTableView.h"

#include "Camera/CameraComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/Texture2D.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "UObject/ConstructorHelpers.h"
#include "YgoFeel.h"
#include "YgoLab.h"

namespace
{
	constexpr float VideoDistance = 5000.f;  // cm: far behind the table, so every effect is drawn over it
	constexpr float MaxShakeDegrees = 1.1f;  // at full trauma
	FVector ToUnrealDir(const FVector3d& V) { return FVector(V.X, V.Y, -V.Z); }
}

AYgoTableView::AYgoTableView()
{
	PrimaryActorTick.bCanEverTick = true;
	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	SetRootComponent(Root);
	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(Root);
	Camera->bConstrainAspectRatio = true;
	VideoPlane = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Video"));
	VideoPlane->SetupAttachment(Root);
	VideoPlane->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	VideoPlane->CastShadow = false;
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Plane(TEXT("/Engine/BasicShapes/Plane.Plane"));
	if (Plane.Succeeded()) VideoPlane->SetStaticMesh(Plane.Object);

	// The video must come out as the camera filmed it: fixed exposure, no filmic curve, no vignette,
	// and bloom only above 1 (the effects' HDR light), never from the video itself.
	FPostProcessSettings& PP = Camera->PostProcessSettings;
	PP.bOverride_AutoExposureMethod = true; PP.AutoExposureMethod = AEM_Manual;
	PP.bOverride_AutoExposureBias = true; PP.AutoExposureBias = 0.f;
	PP.bOverride_AutoExposureApplyPhysicalCameraExposure = true; PP.AutoExposureApplyPhysicalCameraExposure = false;
	PP.bOverride_ToneCurveAmount = true; PP.ToneCurveAmount = 0.f;
	PP.bOverride_BlueCorrection = true; PP.BlueCorrection = 0.f;
	PP.bOverride_ExpandGamut = true; PP.ExpandGamut = 0.f;
	PP.bOverride_VignetteIntensity = true; PP.VignetteIntensity = 0.f;
	PP.bOverride_LocalExposureHighlightContrastScale = true; PP.LocalExposureHighlightContrastScale = 1.f;
	PP.bOverride_LocalExposureShadowContrastScale = true; PP.LocalExposureShadowContrastScale = 1.f;
	PP.bOverride_BloomThreshold = true; PP.BloomThreshold = 1.f;
	PP.bOverride_BloomIntensity = true; PP.BloomIntensity = 1.2f;
}

void AYgoTableView::BeginPlay()
{
	Super::BeginPlay();
	if (UMaterialInterface* M = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/YgoAR/M_Video.M_Video")))
	{
		VideoMaterial = UMaterialInstanceDynamic::Create(M, this);
		VideoPlane->SetMaterial(0, VideoMaterial);
	}
	else
	{
		UE_LOG(LogTemp, Error, TEXT("Falta /Game/YgoAR/M_Video: corre Scripts/make_assets.py (README.md)"));
	}
	if (UYgoLab* Lab = UYgoLab::Get(this))
	{
		Lab->OnScene.AddUObject(this, &AYgoTableView::ApplyScene);
		Lab->OnFrame.AddUObject(this, &AYgoTableView::ApplyFrame);
	}
	ApplyScene();
}

void AYgoTableView::ApplyScene()
{
	const UYgoLab* Lab = UYgoLab::Get(this);
	const FYgoScene Scene = Lab ? Lab->GetScene() : FYgoScene();
	// OpenCV camera axes (image right, image down, forward) in world mm -> Unreal (z up, cm).
	const FVector Forward = ToUnrealDir(Scene.Axis(2)).GetSafeNormal();
	const FVector Right = ToUnrealDir(Scene.Axis(0)).GetSafeNormal();
	const FVector Up = -ToUnrealDir(Scene.Axis(1)).GetSafeNormal();
	const FVector Location = FYgoScene::ToUnreal(Scene.CameraCentreMm());
	BaseRotation = FRotationMatrix::MakeFromXZ(Forward, Up).Rotator();
	Camera->SetWorldLocationAndRotation(Location, BaseRotation);
	Camera->SetFieldOfView(Scene.HorizontalFovDeg());
	Camera->SetAspectRatio(float(Scene.ImageSize.X) / Scene.ImageSize.Y);

	// The video plane fills the camera's frustum at VideoDistance. Plane mesh: 100 x 100 cm in its XY,
	// facing +Z; its X runs along the image's right, its Y down the image, its Z back at the camera.
	const double Width = 2 * VideoDistance * FMath::Tan(FMath::DegreesToRadians(Scene.HorizontalFovDeg()) / 2);
	const double Height = Width * Scene.ImageSize.Y / Scene.ImageSize.X;
	const FVector Centre = Location + Forward * VideoDistance
		+ Right * ((Scene.ImageSize.X / 2.0 - Scene.Cx) / Scene.Fx * VideoDistance)
		+ Up * ((Scene.Cy - Scene.ImageSize.Y / 2.0) / Scene.Fy * VideoDistance);
	VideoPlane->SetWorldLocationAndRotation(Centre, FRotationMatrix::MakeFromXZ(Right, -Forward).Rotator());
	VideoPlane->SetWorldScale3D(FVector(Width / 100.0, Height / 100.0, 1));
}

void AYgoTableView::ApplyFrame()
{
	const UYgoLab* Lab = UYgoLab::Get(this);
	UTexture2D* Video = Lab ? Lab->GetVideo() : nullptr;
	if (Video && Video != ShownVideo && VideoMaterial)
	{
		VideoMaterial->SetTextureParameterValue(TEXT("Video"), Video);
		ShownVideo = Video;
	}
}

FVector AYgoTableView::CameraLocation() const
{
	return Camera->GetComponentLocation();
}

void AYgoTableView::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	// Screen shake as a small rotation about the camera centre: the video and the effects move together.
	UYgoFeel* Feel = UYgoFeel::Get(this);
	const float Shake = Feel ? Feel->Shake(DeltaSeconds) : 0.f;
	if (Shake > 0)
	{
		const float Now = GetWorld()->GetTimeSeconds(), A = MaxShakeDegrees * Shake;
		Camera->SetWorldRotation(BaseRotation + FRotator(FMath::Sin(Now * 71.f) * A, FMath::Sin(Now * 53.f + 1.3f) * A, 0));
		bShaking = true;
	}
	else if (bShaking)
	{
		bShaking = false;
		Camera->SetWorldRotation(BaseRotation);
	}
}
