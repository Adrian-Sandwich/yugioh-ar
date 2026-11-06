// The real camera, in Unreal: a virtual camera with the lab camera's pose and field of view over the
// table (/scene), and the live video on a plane filling its view far behind the table. Effects are
// placed in table coordinates and line up with the video.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "YgoTableView.generated.h"

class UCameraComponent;
class UStaticMeshComponent;
class UMaterialInstanceDynamic;
class UTexture2D;

UCLASS()
class AYgoTableView : public AActor
{
	GENERATED_BODY()
public:
	AYgoTableView();
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	UCameraComponent* GetCamera() const { return Camera; }
	// Where the camera is, in Unreal units (cm), for billboards.
	FVector CameraLocation() const;

private:
	void ApplyScene();
	void ApplyFrame();

	UPROPERTY(VisibleAnywhere) TObjectPtr<USceneComponent> Root;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UCameraComponent> Camera;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UStaticMeshComponent> VideoPlane;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> VideoMaterial;
	UPROPERTY() TObjectPtr<UTexture2D> ShownVideo;

	FRotator BaseRotation = FRotator::ZeroRotator;
	bool bShaking = false;
};
