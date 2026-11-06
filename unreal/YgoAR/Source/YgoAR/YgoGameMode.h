// No map, no pawn: the game mode builds the table view, the stage and the HUD in code.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "YgoGameMode.generated.h"

class SYgoHud;

UCLASS()
class AYgoGameMode : public AGameModeBase
{
	GENERATED_BODY()
public:
	AYgoGameMode();
	virtual void StartPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type Reason) override;

private:
	TSharedPtr<SYgoHud> Hud;
};
