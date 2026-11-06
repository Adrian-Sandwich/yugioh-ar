// The duel's HUD over the 3D view (Slate, in code). The table is the focus: life points in cartouches
// at the two players' corners, the phases as a row of tiles, and a title card for the play being made.
// When the notary needs a decision a prompt opens by the near player's hand; what has no answer stays a
// quiet note until asked for. Everything shown comes from /duel, every answer goes back to it (UYgoLab).
// Mouse or keyboard: 1-9 answer, Tab next question, Esc later, Space next phase, Z undo the last play.
#pragma once

#include "CoreMinimal.h"
#include "Fonts/CompositeFont.h"
#include "Styling/SlateBrush.h"
#include "Styling/SlateTypes.h"
#include "Widgets/SCompoundWidget.h"
#include "YgoTypes.h"

class UYgoFeel;
enum class EYgoSound : uint8;
class UYgoLab;
class FJsonObject;
class SBox;
class SHorizontalBox;
class SVerticalBox;

class SYgoHud : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SYgoHud) {}
		SLATE_ARGUMENT(TWeakObjectPtr<UYgoLab>, Lab)
		SLATE_ARGUMENT(TWeakObjectPtr<UYgoFeel>, Feel)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);
	virtual void Tick(const FGeometry& Geometry, const double CurrentTime, const float DeltaTime) override;
	virtual bool SupportsKeyboardFocus() const override { return true; }
	virtual FReply OnKeyDown(const FGeometry& Geometry, const FKeyEvent& Event) override;

	// A title card over the table: the card's name and what is happening to it.
	void ShowBanner(const FText& Title, const FText& Subtitle, const FLinearColor& Accent);
	// The whole view washed with a colour that fades out (a trap springing, a hit).
	void Flash(const FLinearColor& Color, float Alpha, float Seconds);
	// A life point change's flash, jolt and floating number without the duel's change (AYgoStage's demo).
	void PreviewLp(int32 Player, int32 Delta);
	// The question on screen, whose zone the stage marks on the table; null when the prompt is closed.
	const FYgoQuestion* AskedQuestion() const;
	// A monster clicked on the table, in the Battle Phase: yours picks the attacker, a rival's is the target.
	void PickCard(const FString& CopyId);
	const FString& Attacker() const { return AttackerId; }
	bool ShowsZones() const { return bZones; }

private:
	TSharedRef<SWidget> PlayerPanel(int32 Player);
	TSharedRef<SWidget> PhaseBar();
	TSharedRef<SWidget> PromptPanel();
	TSharedRef<SWidget> PlayPanel();
	TSharedRef<SWidget> StartPanel();  // begins the duel, or tells how it ended and offers the next
	// A plate that acts when pressed. Never takes keyboard focus: the keys stay with the HUD.
	TSharedRef<SWidget> Action(const TAttribute<FText>& Label, TFunction<void()> Do, TAttribute<bool> Enabled, int32 Size = 15,
		TAttribute<bool> Chosen = false, const FLinearColor& TextColor = FLinearColor(1, .93f, .78f));
	FSlateFontInfo Display(float Size, FName Face = TEXT("Bold")) const;  // Cinzel: names, numbers, labels
	const FYgoDuel* Duel() const;
	FLinearColor Accent(int32 Player) const;
	bool Live() const;  // a duel in play, and no answer on its way
	FText Sentence(const FYgoQuestion& Q) const;

	void Send(const TSharedRef<FJsonObject>& Event);
	void GotoPhase(int32 Phase);
	void EndTurn();
	void NextPhase();
	void Answer(const FYgoQuestion& Q, const FYgoOption& Option);
	void Revise(const FString& Id, const FString& Replacement);
	void Attack(const TSharedPtr<FJsonValue>& Target);
	void StartDuel(int32 Starting);
	void Note(const FText& Text);  // a line about the HUD itself: sound off, calm mode
	void Sound(EYgoSound Which, float Volume = 1.f) const;
	void StepQuestion();
	void CloseQuestion();
	bool PromptOpen() const;
	void SelectQuestion();
	void RebuildPrompt();
	void RebuildPlay(const FYgoPlay& Play);
	const FYgoQuestion* FindQuestion(const FString& Key) const;

	TWeakObjectPtr<UYgoLab> Lab;
	TWeakObjectPtr<UYgoFeel> Feel;
	TSharedPtr<FStandaloneCompositeFont> Cinzel;
	FButtonStyle Plain;
	double Now = 0;
	float ShownLp[2] = {8000, 8000};
	int32 LastLp[2] = {-1, -1};
	double LpChangedAt[2] = {-100, -100};
	bool bLpHurt[2] = {true, true};
	int32 LpDelta[2] = {0, 0};  // the last change, floating by the panel

	FLinearColor FlashColor = FLinearColor::White;
	float FlashAlpha = 0, FlashSeconds = 1;
	double FlashAt = -100;

	TSharedPtr<SWidget> Banner;
	FText BannerTitle, BannerSubtitle;
	FLinearColor BannerAccent = FLinearColor::White;
	double BannerAt = -100;

	// The prompt: the notary's question or the attack to resolve. Keys, not indices: the list changes.
	bool bBusy = false;            // an answer is on its way: nothing else can be sent
	FString AttackerId;            // the monster picked to attack
	bool bZones = false;           // the board's zones are drawn on the table
	bool bWasOpen = false;
	double TickAt = 0;             // the next tick of the life points counting
	bool bErrorIsNote = false;
	FString AskedKey;
	TSet<FString> Later;           // closed for now by the player, on this screen only
	bool bListOpen = false;        // the notes without an answer were asked for
	TSet<FString> Tributes;        // copy ids chosen for a Level 5+ summon
	TArray<TFunction<void()>> Keyed;  // what 1-9 do right now
	FString PromptKey;
	TSharedPtr<SVerticalBox> PromptBody;
	FText ErrorText;
	double ErrorAt = -100;

	// The last play the notary recorded, and how to correct it.
	FString LastPlayId;
	FText PlayText, PlayWarning;
	double PlayAt = -100;
	TSharedPtr<SWidget> PlayRoot;
	TSharedPtr<SHorizontalBox> PlayActions;
	TFunction<void()> UndoPlay;

	TArray<TSharedPtr<FSlateBrush>> Brushes;  // kept alive for the widgets that draw them
	const FSlateBrush* Rounded(const FLinearColor& Fill, float Radius, const FLinearColor& Outline = FLinearColor::Transparent, float OutlineWidth = 0);
};
