// What the lab serves (camera_viewer.py), parsed: tracks of the newest frame, the camera over the
// table (/scene, scene3d.py) and the duel (/duel, table_duel.TableDuel.view).
#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonValue.h"

// One card the tracker follows in the newest frame (X-Tracks header of /snapshot).
struct FYgoTrack
{
	FString TrackId;
	FString CardId;
	FString Name;
	FString SpriteRef;
	FString SpriteUrl;   // only automatic sprites carry one (/sprite/auto:...?v=)
	FVector2D Corners[4];  // image pixels: card TL, TR, BR, BL
	bool bStable = false;

	FVector2D Center() const { return (Corners[0] + Corners[1] + Corners[2] + Corners[3]) / 4; }
};

struct FYgoZone
{
	int32 Player = 0;
	FString Zone;            // duel_engine names: monster:0-4, spell:0-4, field, extra_monster:0-1
	TArray<FVector2D> Polygon;  // table mm
};

// The camera over the table. World (scene3d.py): mm, x to the near player's right, y toward that
// player, z into the table. Unreal (left-handed, z up, cm) reads it as (x, y, -z) / 10.
struct FYgoScene
{
	bool bValid = false;
	FIntPoint ImageSize = FIntPoint(1920, 1080);
	double Fx = 1500, Fy = 1500, Cx = 960, Cy = 540;
	// Until /scene answers: straight down from 48 cm over the centre of a 60 x 35 cm mat.
	double R[3][3] = {{1, 0, 0}, {0, 1, 0}, {0, 0, 1}};  // world -> camera (OpenCV)
	FVector3d T = FVector3d(-300, -175, 480);             // world -> camera, mm
	FString IntrinsicsSource;
	TArray<FYgoZone> Zones;

	static FVector ToUnreal(const FVector3d& Mm) { return FVector(Mm.X, Mm.Y, -Mm.Z) / 10.0; }
	static FVector TableToUnreal(const FVector2D& Mm, double HeightCm = 0) { return FVector(Mm.X / 10.0, Mm.Y / 10.0, HeightCm); }

	FVector3d CameraCentreMm() const;
	// Camera axes in world mm: image right, image down, forward (rows of R).
	FVector3d Axis(int32 Row) const { return FVector3d(R[Row][0], R[Row][1], R[Row][2]); }
	double HorizontalFovDeg() const { return FMath::RadiansToDegrees(2 * FMath::Atan(ImageSize.X / (2 * Fx))); }
	// Where the ray through an image pixel meets the table (mm); false if it misses it.
	bool ImageToTable(const FVector2D& Pixel, FVector2D& OutMm) const;
	// The duel zone under a table point, or nullptr.
	const FYgoZone* ZoneAt(const FVector2D& Mm) const;
	const FYgoZone* FindZone(int32 Player, const FString& Zone) const;
	// A zone's centre (mm) and the width of a card in it (mm): web/duel.js zoneGeometry, 72 % of the zone.
	static bool ZonePlace(const FYgoZone& Zone, FVector2D& OutCentre, float& OutCardWidth);
};

struct FYgoPlayer
{
	FString Name;
	int32 Lp = 8000;
	int32 Hand = 0, Deck = 0, ExtraDeck = 0, Graveyard = 0, Banished = 0;
};

struct FYgoBoardCard
{
	int32 Player = 0;
	FString Zone;
	FString CopyId;
	FString CardId;
	FString Name;
	FString Position;
	int32 Controller = 0;
	FString Type;  // the card sheet's line ("Monstruo ...", "Magia ...", "Trampa ..."), empty for a face-down card
	TSharedPtr<FJsonValue> RawCopyId;  // as the lab sent it (a number or a text), to send it back
};

struct FYgoZoneRef
{
	int32 Player = 0;
	FString Zone;
};

struct FYgoOption
{
	FString Type;
	FString Label;
};

struct FYgoPlay
{
	FString Id;
	FString Text;
	FString CardId;
	TArray<FYgoOption> Alternatives;  // what else the notary thinks it could have been
	TArray<FString> Warnings;         // a rule it skipped: the players decide
};

// Something the notary could not explain (table_duel.TableDuel.view): an answer, or only a note when
// it has no options (a card out of place, say).
struct FYgoQuestion
{
	FString Key;   // stable: player:zone
	FString Kind;  // unexplained, missing, moved, different_copy, conflict
	int32 Player = 0;
	FString Zone, ZoneLabel, CardName, CardId, Position, ExpectedPosition, Hint;
	int32 Level = 0;
	TSharedPtr<FJsonValue> CopyId, ExpectedCopy;  // as the lab sent them, to send them back
	TArray<FYgoOption> Options;
};

struct FYgoDuel
{
	bool bValid = false;     // /duel answered (the lab runs with a live camera)
	bool bStarted = false;
	int32 Turn = 0;
	int32 Current = 0;
	FString Phase;           // draw, standby, main1, battle, main2, end (duel_engine.PHASES)
	FString Result;          // empty while it is being played
	int32 Winner = -1;       // who won, once it is over; -1 is a draw
	TArray<FYgoPlayer> Players;
	TArray<FYgoBoardCard> Board;
	TArray<FYgoPlay> Recent;  // newest first: the plays the notary recorded
	// The attack declared and not yet resolved: copy ids; no target is a direct attack.
	FString Attacker, Target;
	// What resolving that attack would do: the notary's sentence, and why it cannot be resolved if it cannot.
	bool bBattlePreview = false;
	FString BattleText, BattleOutcome, BattleProblem;
	// Card backs the camera sees right now (whatever the duel recorded): face-down figures come from these.
	TArray<FYgoZoneRef> BacksSeen;
	TArray<FYgoQuestion> Questions;
};
