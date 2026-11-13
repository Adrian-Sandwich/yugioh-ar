// Client of the lab's camera viewer (camera_viewer.py): the newest camera frame with its tracks
// (/snapshot), the camera over the table (/scene) and the duel (/duel), polled over HTTP. The lab
// owns the camera; Unreal only draws (one owner of the camera: PLAN_DE_ACCION.md).
#pragma once

#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "Tickable.h"
#include "Interfaces/IHttpRequest.h"
#include "YgoTypes.h"
#include "YgoLab.generated.h"

class UTexture2D;
class FJsonObject;

UCLASS(config = Game, defaultconfig, meta = (DisplayName = "Yu-Gi-Oh AR"))
class UYgoSettings : public UDeveloperSettings
{
	GENERATED_BODY()
public:
	// camera_viewer.py's address; the command line wins (-LabUrl=http://host:port).
	UPROPERTY(config, EditAnywhere, Category = "Lab")
	FString LabUrl = TEXT("http://127.0.0.1:8765");
};

DECLARE_MULTICAST_DELEGATE(FYgoFrameEvent);

struct FYgoPixels
{
	int32 Width = 0, Height = 0;
	TArray<uint8> Bgra;
	// Channel C (0 blue .. 3 alpha) at a pixel, clamped to the image; 0..1.
	float At(int32 X, int32 Y, int32 C) const
	{
		if (Width <= 0 || Height <= 0) return 0;
		return Bgra[(FMath::Clamp(Y, 0, Height - 1) * Width + FMath::Clamp(X, 0, Width - 1)) * 4 + C] / 255.f;
	}
};

UCLASS()
class UYgoLab : public UGameInstanceSubsystem, public FTickableGameObject
{
	GENERATED_BODY()
public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;

	// FTickableGameObject
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(UYgoLab, STATGROUP_Tickables); }
	virtual bool IsTickable() const override { return !IsTemplate(); }
	virtual ETickableTickType GetTickableTickType() const override { return IsTemplate() ? ETickableTickType::Never : ETickableTickType::Always; }

	static UYgoLab* Get(const UObject* WorldContext);

	// The newest decoded camera frame (null until the first one) and its tracks.
	UTexture2D* GetVideo() const { return Video; }
	const TArray<FYgoTrack>& GetTracks() const { return Tracks; }
	const FYgoScene& GetScene() const { return Scene; }
	const FYgoDuel& GetDuel() const { return Duel; }
	bool IsConnected() const { return FPlatformTime::Seconds() - LastFrameAt < 3.0; }
	double SecondsSinceStart() const { return FPlatformTime::Seconds() - StartedAt; }

	// "monster", "spell", "trap"; empty while /card-info has not answered, "?" if it could not say.
	FString CardType(const FString& CardId);
	FString CardName(const FString& CardId);
	// The card's cut-out sprite (transparent PNG), or null while it loads or if there is none.
	UTexture2D* Sprite(const FYgoTrack& Track);
	// Any PNG the lab serves (/fx/...), or null while it loads or if there is none.
	UTexture2D* Image(const FString& Path);
	// A PNG that holds numbers, not colour (a relief map): sampled as written, and its pixels are kept.
	UTexture2D* DataImage(const FString& Path);
	// A data image's pixels (BGRA, rows from the top), or null while it loads.
	const FYgoPixels* Pixels(const FString& Path) const { return Kept.Find(Path); }
	// A player's decision (POST /duel). Done gets the lab's reason if it refused, empty if it took it;
	// the duel it answers with is already in GetDuel().
	void Act(const TSharedRef<FJsonObject>& Event, TFunction<void(const FString& Error)> Done);

	FYgoFrameEvent OnFrame;   // a new frame and its tracks
	FYgoFrameEvent OnScene;   // the camera over the table changed
	FYgoFrameEvent OnDuel;    // a new duel state

private:
	void RequestSnapshot();
	// GET a JSON object; Done gets null for any failure (404 included) and the raw body.
	void RequestJson(const FString& Path, TFunction<void(TSharedPtr<FJsonObject>, const FString&)> Done);
	void ParseTracks(const FString& Header);
	void ParseScene(const TSharedPtr<FJsonObject>& Json);
	void ParseDuel(const TSharedPtr<FJsonObject>& Json);
	void UploadFrame(TArray<uint8>&& Bgra, int32 Width, int32 Height);
	// A PNG at Path, cached under Key: null until it arrives.
	UTexture2D* Png(const FString& Key, const FString& Path, bool bData = false);
	static UTexture2D* TextureFromPng(const TArray<uint8>& Png, bool bData, FYgoPixels* OutPixels);

	FString BaseUrl;
	double StartedAt = 0, LastFrameAt = -100, NextDuelAt = 0, NextSceneAt = 0, NextAnalysisAt = 0;
	bool bSnapshotInFlight = false, bDecoding = false, bDuelInFlight = false, bSceneInFlight = false, bAnalysisInFlight = false;
	int64 AnalysisSequence = -1;
	FString LastSceneKey;

	UPROPERTY()
	TObjectPtr<UTexture2D> Video;
	TArray<FYgoTrack> Tracks;
	TArray<FYgoTrack> PendingTracks;  // tracks of the frame being decoded
	FYgoScene Scene;
	FYgoDuel Duel;

	struct FSheet { FString Type; FString Name; };
	TMap<FString, TOptional<FSheet>> Sheets;  // unset: requested, not answered yet
	UPROPERTY()
	TMap<FString, TObjectPtr<UTexture2D>> Sprites;
	TSet<FString> SpritesRequested;
	TMap<FString, FYgoPixels> Kept;  // data images' pixels, by path
};
