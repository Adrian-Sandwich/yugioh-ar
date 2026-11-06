// Short effects on the table, the 3D versions of web/duel.js's 'activate' (a spell, a trap), 'set'
// and 'impact': the same beats and colours, stretched by 1.5 for the 3D view (as the summon,
// YgoSummonFx). Sizes are in the 2D view's plane units (onPlane: 1 = 0.44 card widths).
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "YgoFx.generated.h"

class SYgoHud;
class UMaterialInstanceDynamic;
class UStaticMesh;
class UStaticMeshComponent;
class UYgoParticles;
class AYgoTableView;

enum class EYgoFx : uint8
{
	Spell,   // a magic circle opens with a back easing, a soft pillar, glyphs rising
	Trap,    // a hexagon snaps shut, chains whip out; a jolt and a pink flash
	Set,     // a card set face-down: the back's swirl gathers into the zone
	Impact,  // an attack lands: a flash of light, a ring over the table, sparks
};

UCLASS()
class AYgoFx : public AActor
{
	GENERATED_BODY()
public:
	AYgoFx();
	// What, where (a table point, cm), how big (the card's width there, cm) and in which colour; the
	// view to shake, the particles to emit with and the HUD to flash.
	void Start(EYgoFx Kind, const FVector& Where, float CardWidthCm, const FLinearColor& Color,
		AYgoTableView* View, UYgoParticles* Particles, TSharedPtr<SYgoHud> Hud);
	virtual void Tick(float DeltaSeconds) override;

	static float Duration(EYgoFx Kind);

private:
	void Fire();
	double Clock() const;
	UStaticMeshComponent* Make(const TCHAR* Name, UStaticMesh* Mesh, int32 SortPriority);
	// A flat plane on the table, centred on the effect, Radius cm from its centre to its edge.
	static void Lay(UStaticMeshComponent* Plane, float Radius, float Height = 0);

	UPROPERTY() TObjectPtr<UStaticMeshComponent> Disc;  // the kind's drawing on the table (M_FxMagic)
	UPROPERTY() TObjectPtr<UStaticMeshComponent> Glow;
	UPROPERTY() TObjectPtr<UStaticMeshComponent> Beam;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> DiscFx;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> GlowFx;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> BeamFx;
	TWeakObjectPtr<AYgoTableView> View;
	TWeakObjectPtr<UYgoParticles> Particles;
	TSharedPtr<SYgoHud> Hud;
	EYgoFx Kind = EYgoFx::Spell;
	FLinearColor Color = FLinearColor::White;
	float Width = 6.f, Seed = 0.f;
	double StartedAt = 0;  // UYgoFeel's clock, as the figures (AYgoStage)
	bool bFired = false;
};
