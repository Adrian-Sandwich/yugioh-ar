#include "YgoGameMode.h"

#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "YgoFeel.h"
#include "YgoHud.h"
#include "YgoLab.h"
#include "YgoStage.h"
#include "YgoTableView.h"

AYgoGameMode::AYgoGameMode()
{
	DefaultPawnClass = nullptr;
}

void AYgoGameMode::StartPlay()
{
	Super::StartPlay();
	GAreScreenMessagesEnabled = false;  // the engine's debug text ("Preparing Shaders") is not part of the view
	UWorld* World = GetWorld();
	AYgoTableView* View = World->SpawnActor<AYgoTableView>();
	AYgoStage* Stage = World->SpawnActor<AYgoStage>();
	if (APlayerController* PC = World->GetFirstPlayerController()) PC->SetViewTarget(View);
	if (GEngine && GEngine->GameViewport)
		GEngine->GameViewport->AddViewportWidgetContent(SAssignNew(Hud, SYgoHud).Lab(UYgoLab::Get(this)).Feel(UYgoFeel::Get(this)), 10);
	if (APlayerController* PC = World->GetFirstPlayerController(); PC && Hud.IsValid())
	{
		// The HUD answers the notary: pointer always there, keys for the HUD, the window free to leave.
		PC->bShowMouseCursor = true;
		FInputModeGameAndUI Input;
		Input.SetWidgetToFocus(Hud);
		Input.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
		Input.SetHideCursorDuringCapture(false);
		PC->SetInputMode(Input);
	}
	Stage->Setup(View, Hud);
}

void AYgoGameMode::EndPlay(const EEndPlayReason::Type Reason)
{
	if (Hud.IsValid() && GEngine && GEngine->GameViewport) GEngine->GameViewport->RemoveViewportWidgetContent(Hud.ToSharedRef());
	Hud.Reset();
	Super::EndPlay(Reason);
}
