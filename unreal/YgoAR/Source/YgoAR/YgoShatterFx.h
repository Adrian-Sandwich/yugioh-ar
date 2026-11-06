// A destroyed monster breaking apart, the 3D version of web/duel.js's 'destroy': its figure's cut-out
// in 6 x 6 pieces that fly out, spin and fall, glowing orange as they break and burning out, while
// embers rise and a fire glow fades. (The 2D smoke is left out: the particles here only add light.)
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "YgoShatterFx.generated.h"

class UInstancedStaticMeshComponent;
class UMaterialInstanceDynamic;
class UStaticMeshComponent;
class UTexture2D;
class UYgoParticles;
class AYgoTableView;

UCLASS()
class AYgoShatterFx : public AActor
{
	GENERATED_BODY()
public:
	AYgoShatterFx();
	// The figure as last drawn: its cut-out's centre and axes (X right, Y down the image, Z at the
	// camera; no scale), its size (cm), its card's width (cm) and its sprite.
	void Start(const FTransform& Figure, const FVector2D& SizeCm, float CardWidthCm, UTexture2D* Sprite,
		AYgoTableView* View, UYgoParticles* Particles);
	virtual void Tick(float DeltaSeconds) override;

	static constexpr float Duration = 1.6f;  // 2D: 1.1 s
	static constexpr int32 Cells = 6;        // pieces per side (M_FxShard)

private:
	double Clock() const;
	UPROPERTY() TObjectPtr<UInstancedStaticMeshComponent> Shards;
	UPROPERTY() TObjectPtr<UStaticMeshComponent> Glow;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> GlowFx;
	FTransform Figure;
	FVector2D Size = FVector2D(6, 8);
	float Width = 6.f;
	double StartedAt = 0;
};
