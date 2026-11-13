// The stage: what the camera sees, turned into 3D, with web/duel.js's rules so both views agree.
// Every card on the field gets its figure on its card: a monster its approved cut-out sprite over a
// light ring, a spell or a trap its own (hovering, or restless) over its kind's emblem, a card back
// in a Monster Zone the Millennium shield turning (a solid of gold and lacquer). The camera drives the entrances (noticeArrivals):
// a card new in its zone is summoned or activated, a new back is set. From the duel only the
// players' decisions (stageEvents): attacks, destruction, life points.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "YgoTypes.h"
#include "YgoStage.generated.h"

class AYgoTableView;
class SYgoHud;
class UMaterialInstanceDynamic;
class UProceduralMeshComponent;
class UStaticMeshComponent;
class UTexture2D;
class UYgoParticles;

UCLASS()
class AYgoStage : public AActor
{
	GENERATED_BODY()
public:
	AYgoStage();
	void Setup(AYgoTableView* View, TSharedPtr<SYgoHud> Hud);
	virtual void Tick(float DeltaSeconds) override;

private:
	// A card on the table: centre (mm), width (mm) and the image's "down" on the table plane.
	struct FPlace { FVector2D Centre; float Width = 59.f; FVector2D Down = FVector2D(0, 1); };
	struct FFigure
	{
		FYgoTrack Track;
		FString Kind = TEXT("monster");  // monster, spell, trap
		FPlace Target;
		FVector Centre = FVector::ZeroVector;  // cm, smoothed
		FVector Down = FVector(0, 1, 0);
		float Width = 5.9f;
		double LastSeen = 0, SummonAt = -100, ActivateAt = -100, AttackAt = -100;
		FVector AttackTo = FVector::ZeroVector;  // where the attack lands (table, cm)
		bool bImpact = false, bDash = false;
		float Seed = 0;
		bool bRival = false;
		TObjectPtr<UStaticMeshComponent> Sprite, Base, Shadow, Shield;
		TObjectPtr<UMaterialInstanceDynamic> SpriteFx, BaseFx, ShadowFx, ShieldFx;
		TObjectPtr<UStaticMeshComponent> Ghosts[3];  // after-images of an attack's dash
		TObjectPtr<UMaterialInstanceDynamic> GhostFx[3];
	};
	// Where a monster's figure was last drawn: its destruction comes after its card has left the table.
	struct FPose
	{
		FTransform Quad;  // the cut-out's centre and axes (X right, Y down the image, Z at the camera)
		FVector2D Size;   // cm
		FVector Card = FVector::ZeroVector;  // its card on the table, cm
		float Width = 5.9f;
		TWeakObjectPtr<UTexture2D> Sprite;
		double At = 0;
	};
	// A card back the camera sees in a zone (the duel's backs_seen).
	struct FBack
	{
		FVector Centre = FVector::ZeroVector;  // cm
		float Width = 5.9f;                    // a card's, cm
		double LastSeen = 0, SetAt = -100;
		float Seed = 0;
		TObjectPtr<UStaticMeshComponent> Glow, Shadow;  // the shadow and the shield only in a Monster Zone
		TObjectPtr<UMaterialInstanceDynamic> GlowFx, ShadowFx, SolidFx;
		TObjectPtr<UProceduralMeshComponent> Solid;     // the shield: a solid mesh built from its relief maps
		bool bSolidBuilt = false;
	};

	void OnFrame();
	void OnDuel();
	bool PlaceOf(const FYgoTrack& Track, FPlace& Out) const;
	// "monster", "spell" or "trap"; empty while the card's sheet is on its way.
	FString KindOf(const FYgoTrack& Track);
	void Arrive(const FYgoTrack& Track, const FPlace& Place, const FString& Kind, int32 Player);
	void Attack(const FString& Attacker, const FString& Target);
	void Shatter(const FString& CopyId);
	void SeeBacks(const FYgoDuel& Duel, double Now);
	FFigure& FigureFor(const FYgoTrack& Track);
	void UpdateFigure(FFigure& F, float Dt, double Now);
	void UpdateBack(FBack& B, float Dt, double Now);
	void DropFigure(FFigure& F);
	void DropBack(FBack& B);
	// Which way is up for a figure: straight up when the camera looks at the table from the side;
	// when it looks straight down (Lean 1), toward the image's top, lying on the table as in the 2D view.
	void Upright(FVector& OutUp, float& OutLean) const;
	FVector TableDown() const;  // the image's "down" over the table
	void UpdateAskMark(double Now);  // the zone of the question on screen, marked on the table
	void UpdateZoneMarks();          // every zone of the board, while the HUD asks for them
	void PickWithMouse();            // a click on a monster, in the Battle Phase
	double Clock() const;            // figures and effects: UYgoFeel's, which a blow can freeze
	void Motes(const FVector& Centre, float Width, const FLinearColor& Color, float PerSecond, float Dt, const FVector& Up);
	UStaticMeshComponent* NewPlane(const TCHAR* Material, UMaterialInstanceDynamic*& OutFx, int32 SortPriority);
	FLinearColor OwnerColor(const FString& Kind, bool bRival) const;
	void Capture(double Now);

	UPROPERTY() TObjectPtr<UYgoParticles> Particles;
	// A speck in front of the camera with the shield's material, from the start: its shaders load on
	// first use, and the first shield of a session would come in black while they do.
	UPROPERTY() TObjectPtr<UProceduralMeshComponent> Warm;
	UPROPERTY() TObjectPtr<UStaticMeshComponent> AskMark;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> AskMarkFx;
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> ZoneMarks;
	UPROPERTY() TArray<TObjectPtr<UMaterialInstanceDynamic>> ZoneMarkFx;
	TWeakObjectPtr<AYgoTableView> View;
	TSharedPtr<SYgoHud> Hud;
	TMap<FString, FFigure> Figures;      // by track id (= the duel's copy id)
	TMap<FString, double> Arrived;       // player|zone|card -> last seen
	TMap<FString, FPose> Poses;          // by copy id
	TMap<FString, double> Shattered;     // copy id -> until when its figure stays broken
	TArray<TPair<FString, double>> ShatterAt;  // copy id, when: a battle's victim breaks as the blow lands
	TMap<FString, FBack> Backs;          // by player|zone
	TMap<FString, double> BackArrived;   // player|zone -> last seen
	FYgoDuel Prev;
	double StartedAt = 0;             // first tick; 0 before it
	// -YgoReplay=<s>: that long after the first tick, the cards on the table make their entrance again
	// (to see a summon without moving cards, once loading hitches are over).
	double ReplayAt = 0;
	// -YgoDemo=<s>: that long after the first tick, a show of every animation with the cards on the
	// table (entrances, a spell, a trap, an attack and its victim breaking, a direct hit): to check
	// the look without playing a turn.
	double DemoAt = 0;
	int32 DemoStep = 0;
	void Demo(double Since);

	// -YgoShots=<dir> [-YgoShotEvery=<s>]: screenshots for checking the look; -YgoQuitAfter=<s>: exit then.
	FString ShotDir;
	float ShotEvery = 0, QuitAfter = 0;
	double NextShotAt = 0;
	int32 ShotCount = 0;
};
