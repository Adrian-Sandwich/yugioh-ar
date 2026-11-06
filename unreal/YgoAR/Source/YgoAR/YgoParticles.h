// Particles of every effect, one instanced mesh: camera-facing quads (dots) or quads stretched along
// their velocity (sparks), with gravity and drag, coloured per instance (PerInstanceCustomData:
// r, g, b in HDR, alpha). Authored in code because Niagara systems are binary editor assets.
#pragma once

#include "CoreMinimal.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "YgoParticles.generated.h"

struct FYgoParticle
{
	FVector Position = FVector::ZeroVector;   // cm
	FVector Velocity = FVector::ZeroVector;   // cm/s
	FLinearColor Color = FLinearColor::White; // HDR: above 1 blooms
	float Size = 1.f;                         // cm
	float Life = 1.f;                         // s
	float Age = 0.f;
	float Gravity = 0.f;                      // cm/s^2, along -Z (down to the table)
	float Drag = 0.f;                         // fraction of speed lost per second
	float Stretch = 0.f;                      // sparks: length = Size + Stretch * speed
	float Delay = 0.f;                        // s before it appears
};

UCLASS()
class UYgoParticles : public UInstancedStaticMeshComponent
{
	GENERATED_BODY()
public:
	UYgoParticles();
	void Emit(const FYgoParticle& P);
	// Called by the stage every frame with the camera's position.
	void Step(float DeltaSeconds, const FVector& CameraLocation);

private:
	TArray<FYgoParticle> Live;
	int32 Shown = 0;
	static constexpr int32 MaxParticles = 1500;
};
