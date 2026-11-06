#include "YgoFeel.h"

#include "Engine/GameInstance.h"
#include "Engine/World.h"
#include "Kismet/GameplayStatics.h"
#include "Sound/SoundBase.h"

namespace
{
	constexpr float DecayPerSecond = 1.5f;
	struct FWeight { float Trauma; double Freeze; };
	constexpr FWeight Weights[] = {{.3f, 0.}, {.5f, .05}, {.85f, .1}};
	struct FEntry { const TCHAR* Name; float Volume; };
	// Balanced by level, not by ear of the moment: interface ticks stay far below the blows.
	constexpr FEntry Entries[] = {
		{TEXT("card"), .8f}, {TEXT("set"), .8f}, {TEXT("dash"), .9f}, {TEXT("rise"), .55f}, {TEXT("burst"), .6f}, {TEXT("boom"), .6f},
		{TEXT("spell"), .7f}, {TEXT("trap"), .8f}, {TEXT("hit"), 1.f}, {TEXT("shatter"), .8f}, {TEXT("damage"), .7f},
		{TEXT("tick"), .22f}, {TEXT("ask"), .5f}, {TEXT("click"), .45f}, {TEXT("fail"), .6f},
	};
	static_assert(UE_ARRAY_COUNT(Entries) == int32(EYgoSound::Count));
}

UYgoFeel* UYgoFeel::Get(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	UGameInstance* GI = World ? World->GetGameInstance() : nullptr;
	return GI ? GI->GetSubsystem<UYgoFeel>() : nullptr;
}

double UYgoFeel::Seconds()
{
	const double Wall = FPlatformTime::Seconds();
	if (Wall < FrozenUntil) return FrozenFrom - Lost;
	if (FrozenUntil > 0) { Lost += FrozenUntil - FrozenFrom; FrozenUntil = 0; }
	return Wall - Lost;
}

void UYgoFeel::Blow(EYgoWeight Weight)
{
	const FWeight& W = Weights[int32(Weight)];
	AddTrauma(W.Trauma);
	if (bCalm || W.Freeze <= 0) return;
	const double Wall = FPlatformTime::Seconds();
	if (Wall < FrozenUntil) FrozenUntil = FMath::Max(FrozenUntil, Wall + W.Freeze);
	else
	{
		Seconds();  // closes an ended freeze
		FrozenFrom = Wall; FrozenUntil = Wall + W.Freeze;
	}
}

void UYgoFeel::AddTrauma(float Amount)
{
	if (!bCalm) Trauma = FMath::Min(1.f, Trauma + Amount);
}

float UYgoFeel::Shake(float DeltaSeconds)
{
	const float Now = Trauma * Trauma;
	Trauma = FMath::Max(0.f, Trauma - DecayPerSecond * DeltaSeconds);
	return Now;
}

void UYgoFeel::Play(EYgoSound Sound, float Volume)
{
	if (bMuted) return;
	const int32 Index = int32(Sound);
	if (Sounds.IsEmpty()) Sounds.SetNum(int32(EYgoSound::Count));
	if (!Sounds[Index])
		Sounds[Index] = LoadObject<USoundBase>(nullptr, *FString::Printf(TEXT("/Game/YgoAR/Audio/S_%s.S_%s"), Entries[Index].Name, Entries[Index].Name));
	const UGameInstance* GI = GetGameInstance();
	if (Sounds[Index] && GI && GI->GetWorld())
		UGameplayStatics::PlaySound2D(GI->GetWorld(), Sounds[Index], Entries[Index].Volume * Volume, FMath::FRandRange(.96f, 1.04f));  // never quite the same twice
}
