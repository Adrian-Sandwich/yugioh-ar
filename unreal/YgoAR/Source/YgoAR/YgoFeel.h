// How much a moment weighs, in one place so the whole duel stays proportional: the three weights of a
// blow, the camera's trauma, the sounds. Trauma adds up and decays, and the shake is its square, so
// small events barely move the view and big ones punch. A heavy blow also freezes the figures and
// effects for an instant (their clock, Seconds); the camera's video never stops. Calm turns the shake,
// the freeze and the screen flashes off; Mute the sound.
#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "YgoFeel.generated.h"

class USoundBase;

enum class EYgoSound : uint8
{
	Card, Set, Dash, Rise, Burst, Boom, Spell, Trap, Hit, Shatter, Damage, Tick, Ask, Click, Fail, Count
};

enum class EYgoWeight : uint8
{
	Light,   // a card set, a monster shattering
	Medium,  // a summon's burst, a trap springing
	Heavy,   // an attack landing
};

UCLASS()
class UYgoFeel : public UGameInstanceSubsystem
{
	GENERATED_BODY()
public:
	static UYgoFeel* Get(const UObject* WorldContext);

	// The clock of figures and effects: stands still during a freeze.
	double Seconds();
	bool IsFrozen() const { return FPlatformTime::Seconds() < FrozenUntil; }

	void Blow(EYgoWeight Weight);
	void AddTrauma(float Amount);
	// The shake to apply this frame, 0 to 1 (trauma squared), letting the trauma decay.
	float Shake(float DeltaSeconds);

	void Play(EYgoSound Sound, float Volume = 1.f);
	bool IsMuted() const { return bMuted; }
	bool IsCalm() const { return bCalm; }
	void ToggleMute() { bMuted = !bMuted; }
	void ToggleCalm() { bCalm = !bCalm; if (bCalm) Trauma = 0; }

private:
	UPROPERTY() TArray<TObjectPtr<USoundBase>> Sounds;
	float Trauma = 0;
	double FrozenFrom = 0, FrozenUntil = 0, Lost = 0;
	bool bMuted = false, bCalm = false;
};
