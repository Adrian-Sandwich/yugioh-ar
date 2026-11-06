// Summon, the 3D version of web/duel.js's 'summon' (same beats, same colours): a magic circle opens
// on the card, a shockwave and a burst of sparks at 30 %, a pillar of light, motes rising; the
// monster's figure (AYgoStage) appears at 30 % with an overshoot and a white flash.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "YgoSummonFx.generated.h"

class UStaticMeshComponent;
class UMaterialInstanceDynamic;
class UYgoParticles;
class AYgoTableView;

UCLASS()
class AYgoSummonFx : public AActor
{
	GENERATED_BODY()
public:
	AYgoSummonFx();
	// Where (table point, cm), how big (card width, cm), its colour, and what to shake and emit with.
	void Start(const FVector& Where, float CardWidthCm, const FLinearColor& Color, AYgoTableView* View, UYgoParticles* Particles);
	virtual void Tick(float DeltaSeconds) override;

	static constexpr float Duration = 2.2f;

private:
	UMaterialInstanceDynamic* Fx(UStaticMeshComponent* Mesh, const TCHAR* Material);
	void Impact();

	double Clock() const;
	UPROPERTY() TObjectPtr<UStaticMeshComponent> Circle;
	UPROPERTY() TObjectPtr<UStaticMeshComponent> Shock;
	UPROPERTY() TObjectPtr<UStaticMeshComponent> Pillar;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> CircleFx;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> ShockFx;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> PillarFx;
	TWeakObjectPtr<AYgoTableView> View;
	TWeakObjectPtr<UYgoParticles> Particles;
	FLinearColor Color = FLinearColor::White;
	// UYgoFeel's clock, as the figure's reveal in AYgoStage: a hitch skips frames instead of pulling the two apart.
	double StartedAt = 0;
	float Width = 6.f, Seed = 0.f;
	bool bFired = false;
};
