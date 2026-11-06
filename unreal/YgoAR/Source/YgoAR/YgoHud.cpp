#include "YgoHud.h"

#include "Brushes/SlateRoundedBoxBrush.h"
#include "Dom/JsonObject.h"
#include "Framework/Application/SlateApplication.h"
#include "InputCoreTypes.h"
#include "Misc/Paths.h"
#include "Styling/CoreStyle.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SWrapBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Text/STextBlock.h"
#include "YgoEase.h"
#include "YgoFeel.h"
#include "YgoLab.h"
#include "YgoPlate.h"

#define LOCTEXT_NAMESPACE "YgoHud"

namespace
{
	const FLinearColor Cream = FLinearColor::FromSRGBColor(FColor(247, 233, 205));   // names and numbers
	const FLinearColor GoldText = FLinearColor::FromSRGBColor(FColor(232, 192, 116));
	const FLinearColor Muted = FLinearColor::FromSRGBColor(FColor(205, 198, 182));
	const FLinearColor Ink(.008f, .012f, .03f);                                      // text on a gold tile
	const FLinearColor Hurt = FLinearColor::FromSRGBColor(FColor(255, 90, 90));
	const FLinearColor Heal = FLinearColor::FromSRGBColor(FColor(110, 255, 160));
	const TCHAR* PhaseKeys[] = {TEXT("draw"), TEXT("standby"), TEXT("main1"), TEXT("battle"), TEXT("main2"), TEXT("end")};
	const TCHAR* PhaseShort[] = {TEXT("DP"), TEXT("SP"), TEXT("M1"), TEXT("BP"), TEXT("M2"), TEXT("EP")};
	constexpr int32 PhaseBattle = 3, PhaseMain2 = 4, PhaseEnd = 5;
	constexpr float PanelWidth = 430.f, PanelHeight = 104.f, BarWidth = 176.f;
	constexpr double PlaySeconds = 8.0, ErrorSeconds = 6.0;

	FSlateFontInfo Reading(const char* Style, int32 Size) { return FCoreStyle::GetDefaultFontStyle(Style, Size); }

	int32 PhaseIndex(const FString& Phase)
	{
		for (int32 i = 0; i < 6; ++i) if (Phase == PhaseKeys[i]) return i;
		return -1;
	}

	FString IdOf(const TSharedPtr<FJsonValue>& V) { return V.IsValid() ? V->AsString() : FString(); }
	void SetId(const TSharedRef<FJsonObject>& E, const TCHAR* Field, const TSharedPtr<FJsonValue>& V)
	{
		E->SetField(Field, V.IsValid() ? V : MakeShared<FJsonValueNull>());
	}

	FText PositionName(const FString& P)
	{
		if (P == TEXT("attack")) return LOCTEXT("Attack", "ataque");
		if (P == TEXT("defense")) return LOCTEXT("Defense", "defensa");
		if (P == TEXT("facedown_defense")) return LOCTEXT("FacedownDefense", "defensa boca abajo");
		if (P == TEXT("faceup")) return LOCTEXT("Faceup", "boca arriba");
		if (P == TEXT("facedown")) return LOCTEXT("Facedown", "boca abajo");
		return FText::FromString(P);
	}
}

const FSlateBrush* SYgoHud::Rounded(const FLinearColor& Fill, float Radius, const FLinearColor& Outline, float OutlineWidth)
{
	Brushes.Add(MakeShared<FSlateRoundedBoxBrush>(Fill, Radius, Outline, OutlineWidth));
	return Brushes.Last().Get();
}

FSlateFontInfo SYgoHud::Display(float Size, FName Face) const
{
	return Cinzel.IsValid() ? FSlateFontInfo(Cinzel, Size, Face) : FCoreStyle::GetDefaultFontStyle("Bold", Size);
}

const FYgoDuel* SYgoHud::Duel() const
{
	const UYgoLab* L = Lab.Get();
	return L ? &L->GetDuel() : nullptr;
}

FLinearColor SYgoHud::Accent(int32 Player) const
{
	return Player == 0 ? FLinearColor::FromSRGBColor(FColor(95, 242, 255)) : FLinearColor::FromSRGBColor(FColor(255, 196, 92));
}

bool SYgoHud::Live() const
{
	const FYgoDuel* D = Duel();
	return D && D->bStarted && D->Result.IsEmpty() && !bBusy;
}

void SYgoHud::Construct(const FArguments& InArgs)
{
	Lab = InArgs._Lab;
	Feel = InArgs._Feel;
	const FString Fonts = FPaths::ConvertRelativePathToFull(FPaths::ProjectDir() / TEXT("Fonts"));
	if (FPaths::FileExists(Fonts / TEXT("Cinzel-Bold.ttf")))
	{
		Cinzel = MakeShared<FStandaloneCompositeFont>();
		Cinzel->DefaultTypeface.AppendFont(TEXT("Bold"), Fonts / TEXT("Cinzel-Bold.ttf"), EFontHinting::Default, EFontLoadingPolicy::LazyLoad);
		Cinzel->DefaultTypeface.AppendFont(TEXT("Black"), Fonts / TEXT("Cinzel-Black.ttf"), EFontHinting::Default, EFontLoadingPolicy::LazyLoad);
	}
	Plain = FButtonStyle().SetNormal(FSlateNoResource()).SetHovered(FSlateNoResource()).SetPressed(FSlateNoResource()).SetDisabled(FSlateNoResource());

	auto Started = [this] { const FYgoDuel* D = Duel(); return D && D->bValid && D->bStarted; };
	ChildSlot
	[
		SNew(SOverlay)
		.Visibility(EVisibility::SelfHitTestInvisible)
		+ SOverlay::Slot()
		[
			SNew(SBorder)
			.BorderImage(Rounded(FLinearColor::White, 0))
			.Visibility_Lambda([this] { return Now - FlashAt < FlashSeconds ? EVisibility::HitTestInvisible : EVisibility::Collapsed; })
			.BorderBackgroundColor_Lambda([this]
			{
				return FSlateColor(FlashColor.CopyWithNewOpacity(FlashAlpha * (1 - YgoEase::Span(Now - FlashAt, 0, FlashSeconds))));
			})
		]
		+ SOverlay::Slot().HAlign(HAlign_Left).VAlign(VAlign_Bottom).Padding(40)
		[
			PlayerPanel(0)
		]
		+ SOverlay::Slot().HAlign(HAlign_Right).VAlign(VAlign_Top).Padding(40)
		[
			PlayerPanel(1)
		]
		+ SOverlay::Slot().HAlign(HAlign_Center).VAlign(VAlign_Top).Padding(0, 26, 0, 0)
		[
			PhaseBar()
		]
		+ SOverlay::Slot().HAlign(HAlign_Center).VAlign(VAlign_Center).Padding(0, 0, 0, 260)
		[
			SAssignNew(Banner, SVerticalBox)
			.Visibility(EVisibility::Collapsed)
			.RenderTransformPivot(FVector2D(.5f, .5f))
			+ SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center)
			[
				SNew(STextBlock)
				.Text_Lambda([this] { return BannerSubtitle; })
				.Font([this] { FSlateFontInfo F = Display(20); F.LetterSpacing = 300; return F; }())
				.ColorAndOpacity_Lambda([this] { return FSlateColor(BannerAccent); })
				.ShadowOffset(FVector2D(0, 2)).ShadowColorAndOpacity(FLinearColor(0, 0, 0, .8f))
			]
			+ SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center)
			[
				SNew(STextBlock)
				.Text_Lambda([this] { return BannerTitle; })
				.Font(Display(50, TEXT("Black")))
				.ColorAndOpacity(Cream)
				.ShadowOffset(FVector2D(0, 3)).ShadowColorAndOpacity(FLinearColor(0, 0, 0, .85f))
			]
		]
		+ SOverlay::Slot().HAlign(HAlign_Right).VAlign(VAlign_Bottom).Padding(40)
		[
			SNew(SVerticalBox)
			.Visibility(EVisibility::SelfHitTestInvisible)
			+ SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Right)
			[
				PromptPanel()
			]
			+ SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Right).Padding(0, 10, 0, 0)
			[
				SNew(SHorizontalBox)
				.Visibility(EVisibility::SelfHitTestInvisible)
				+ SHorizontalBox::Slot().AutoWidth()
				[
					// Where the cards go: a card outside the zones is not read.
					SNew(SBox)
					.Visibility_Lambda([Started] { return Started() ? EVisibility::SelfHitTestInvisible : EVisibility::Collapsed; })
					[
						Action(LOCTEXT("Zones", "Zonas"), [this] { bZones = !bZones; }, true, 14, TAttribute<bool>::CreateLambda([this] { return bZones; }))
					]
				]
				+ SHorizontalBox::Slot().AutoWidth().Padding(8, 0, 0, 0)
				[
					// What the notary noted but has no answer stays out of the way until asked for.
					SNew(SBox)
					.Visibility_Lambda([this]
					{
						const FYgoDuel* D = Duel();
						return D && D->bStarted && D->Questions.Num() && !PromptOpen() ? EVisibility::SelfHitTestInvisible : EVisibility::Collapsed;
					})
					[
						Action(TAttribute<FText>::CreateLambda([this]
						{
							const FYgoDuel* D = Duel();
							return FText::Format(LOCTEXT("Notes", "{0} {0}|plural(one=aviso,other=avisos)"), D ? D->Questions.Num() : 0);
						}), [this] { bListOpen = true; Later.Reset(); }, true, 14)
					]
				]
			]
		]
		+ SOverlay::Slot().HAlign(HAlign_Center).VAlign(VAlign_Bottom).Padding(0, 0, 0, 44)
		[
			PlayPanel()
		]
		+ SOverlay::Slot().HAlign(HAlign_Center).VAlign(VAlign_Center)
		[
			StartPanel()
		]
		+ SOverlay::Slot().HAlign(HAlign_Center).VAlign(VAlign_Bottom).Padding(0, 0, 0, 168)
		[
			SNew(SBox)
			.MaxDesiredWidth(760)
			.Visibility_Lambda([this] { return Now - ErrorAt < ErrorSeconds ? EVisibility::HitTestInvisible : EVisibility::Collapsed; })
			[
				SNew(SYgoPlate).Radius(12).Rim(3).Body(.97f).Padding(FMargin(20, 9))
				.Accent_Lambda([this] { return bErrorIsNote ? YgoPlate::Gold : Hurt; })
				.Lit_Lambda([this] { return bErrorIsNote ? 0.f : .25f; })
				[
					SNew(STextBlock).Font(Reading("Bold", 17)).ColorAndOpacity(Cream).AutoWrapText(true).Text_Lambda([this] { return ErrorText; })
				]
			]
		]
		+ SOverlay::Slot().HAlign(HAlign_Left).VAlign(VAlign_Top).Padding(20, 16)
		[
			SNew(STextBlock)
			.Font(Reading("Regular", 14))
			.ColorAndOpacity(Cream)
			.ShadowOffset(FVector2D(0, 1)).ShadowColorAndOpacity(FLinearColor(0, 0, 0, .9f))
			.Visibility(EVisibility::HitTestInvisible)
			.Text_Lambda([this]
			{
				const UYgoLab* L = Lab.Get();
				const FYgoDuel* D = Duel();
				if (!L || !L->IsConnected()) return LOCTEXT("NoLink", "Sin video del labo: ¿está corriendo camera_viewer.py?");
				if (!D || !D->bValid) return LOCTEXT("NoDuel", "Sin duelo: el labo no tiene cámara en vivo");
				return FText::GetEmpty();
			})
		]
	];
}

TSharedRef<SWidget> SYgoHud::Action(const TAttribute<FText>& Label, TFunction<void()> Do, TAttribute<bool> Enabled, int32 Size,
	TAttribute<bool> Chosen, const FLinearColor& TextColor)
{
	const TSharedRef<SButton> Button = SNew(SButton)
		.ButtonStyle(&Plain)
		.ContentPadding(0)
		.IsFocusable(false)
		.IsEnabled(Enabled)
		.OnClicked_Lambda([this, Do = MoveTemp(Do)] { Sound(EYgoSound::Click); Do(); return FReply::Handled(); });
	const TWeakPtr<SButton> Weak = Button;
	Button->SetContent(
		SNew(SYgoPlate)
		.Radius(10).Rim(2.5f).Padding(FMargin(14, 6))
		.Lit_Lambda([Weak, Chosen]
		{
			const TSharedPtr<SButton> B = Weak.Pin();
			if (Chosen.Get()) return 1.f;
			return B.IsValid() && B->IsPressed() ? 1.f : B.IsValid() && B->IsHovered() ? .55f : 0.f;
		})
		.Alpha_Lambda([Weak] { const TSharedPtr<SButton> B = Weak.Pin(); return B.IsValid() && B->IsEnabled() ? 1.f : .45f; })
		[
			SNew(STextBlock).Text(Label).Font(Display(Size)).ColorAndOpacity(TextColor)
		]);
	return Button;
}

TSharedRef<SWidget> SYgoHud::PlayerPanel(int32 Player)
{
	auto Lp = [this, Player]() -> int32 { const FYgoDuel* D = Duel(); return D && D->Players.IsValidIndex(Player) ? D->Players[Player].Lp : 8000; };
	auto IsCurrent = [this, Player] { const FYgoDuel* D = Duel(); return D && D->bStarted && D->Current == Player; };
	const FLinearColor A = Accent(Player);
	const float NearKnot = Player == 0 ? 46.f : 34.f, FarKnot = Player == 0 ? 34.f : 46.f;

	return SNew(SBox)
		.WidthOverride(PanelWidth).HeightOverride(PanelHeight)
		.Visibility_Lambda([this] { const FYgoDuel* D = Duel(); return D && D->bValid && D->bStarted ? EVisibility::HitTestInvisible : EVisibility::Collapsed; })
		.RenderTransform_Lambda([this, Player]() -> TOptional<FSlateRenderTransform>
		{
			// A jolt when the life points change, as the 2D HUD.
			const float Since = Now - LpChangedAt[Player];
			return FSlateRenderTransform(FVector2D(Since < .4f ? FMath::Sin(Since * 90.f) * 7.f * (1 - Since / .4f) : 0.f, 0.f));
		})
		[
			SNew(SOverlay)
			+ SOverlay::Slot()
			[
				// A cartouche, tied off on the side away from the screen's edge.
				SNew(SYgoPlate)
				.Radius(PanelHeight / 2).Rim(6).Knot(Player == 0 ? 1.f : -1.f)
				.Padding(FMargin(FarKnot, 8, NearKnot, 8))
				.Accent_Lambda([this, Player, A]
				{
					const float Since = Now - LpChangedAt[Player];
					return Since < .6f ? FMath::Lerp(bLpHurt[Player] ? Hurt : Heal, A, Since / .6f) : A;
				})
				.Lit_Lambda([this, Player, IsCurrent]
				{
					const float Since = Now - LpChangedAt[Player];
					const float Turn = IsCurrent() ? .2f + .07f * FMath::Sin(Now * 2.f) : 0.f;
					return FMath::Max(Turn, Since < .6f ? .9f * (1 - Since / .6f) : 0.f);
				})
				.Sheen_Lambda([this, Player] { return YgoEase::Clamp01((Now - LpChangedAt[Player]) / .7f); })
				[
					SNew(SHorizontalBox)
					+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)
					[
						SNew(STextBlock)
						.Font(Display(52, TEXT("Black")))
						.ColorAndOpacity_Lambda([this, Player]
						{
							const float Since = Now - LpChangedAt[Player];
							return FSlateColor(FMath::Lerp(Cream, bLpHurt[Player] ? Hurt : Heal, Since < 1.2f ? 1 - Since / 1.2f : 0.f));
						})
						.ShadowOffset(FVector2D(0, 2)).ShadowColorAndOpacity(FLinearColor(0, 0, 0, .7f))
						.Text_Lambda([this, Player] { return FText::FromString(FString::FromInt(FMath::RoundToInt(ShownLp[Player]))); })
					]
					+ SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center).Padding(16, 0, 0, 0)
					[
						SNew(SVerticalBox)
						+ SVerticalBox::Slot().AutoHeight()
						[
							SNew(STextBlock)
							.Font(Display(16))
							.ColorAndOpacity(GoldText)
							.Text_Lambda([this, Player]
							{
								const FYgoDuel* D = Duel();
								return D && D->Players.IsValidIndex(Player) ? FText::FromString(D->Players[Player].Name) : FText::GetEmpty();
							})
						]
						+ SVerticalBox::Slot().AutoHeight().Padding(0, 5, 0, 0)
						[
							// Life bar, 8000 = full; red when under 30 %.
							SNew(SOverlay)
							+ SOverlay::Slot()
							[
								SNew(SBox).HeightOverride(6).WidthOverride(BarWidth)
								[
									SNew(SBorder).BorderImage(Rounded(FLinearColor(0, 0, 0, .55f), 3))
								]
							]
							+ SOverlay::Slot().HAlign(HAlign_Left)
							[
								SNew(SBox).HeightOverride(6)
								.WidthOverride_Lambda([this, Player] { return FOptionalSize(BarWidth * FMath::Clamp(ShownLp[Player] / 8000.f, 0.f, 1.f)); })
								[
									SNew(SBorder)
									.BorderImage(Rounded(FLinearColor::White, 3))
									.BorderBackgroundColor_Lambda([this, Player, A] { return FSlateColor(ShownLp[Player] / 8000.f < .3f ? Hurt : A); })
								]
							]
						]
						+ SVerticalBox::Slot().AutoHeight().Padding(0, 4, 0, 0)
						[
							SNew(STextBlock)
							.Font(Display(13))
							.ColorAndOpacity(A)
							.Text(LOCTEXT("YourTurn", "Su turno"))
							.Visibility_Lambda([IsCurrent] { return IsCurrent() ? EVisibility::HitTestInvisible : EVisibility::Hidden; })
						]
					]
				]
			]
			// The change itself floats away from the panel toward the table (2D 'lp'): pops in, drifts, fades.
			+ SOverlay::Slot().HAlign(HAlign_Center).VAlign(VAlign_Center)
			[
				SNew(STextBlock)
				.Font([this] { FSlateFontInfo F = Display(54, TEXT("Black")); F.OutlineSettings.OutlineSize = 4; F.OutlineSettings.OutlineColor = FLinearColor(0, 0, 0, .75f); return F; }())
				.Visibility_Lambda([this, Player] { return Now - LpChangedAt[Player] < 1.6 ? EVisibility::HitTestInvisible : EVisibility::Collapsed; })
				.Text_Lambda([this, Player] { return FText::FromString((LpDelta[Player] > 0 ? TEXT("+") : TEXT("")) + FString::FromInt(LpDelta[Player])); })
				.ColorAndOpacity_Lambda([this, Player]
				{
					return FSlateColor((bLpHurt[Player] ? Hurt : Heal).CopyWithNewOpacity(1 - YgoEase::Span(Now - LpChangedAt[Player], 1.12f, 1.6f)));
				})
				.ShadowOffset(FVector2D(0, 0)).ShadowColorAndOpacity_Lambda([this, Player] { return (bLpHurt[Player] ? Hurt : Heal).CopyWithNewOpacity(.6f); })
				.RenderTransformPivot(FVector2D(.5f, .5f))
				.RenderTransform_Lambda([this, Player]() -> TOptional<FSlateRenderTransform>
				{
					const float T = (Now - LpChangedAt[Player]) / 1.6f;
					const float Dir = Player == 0 ? -1.f : 1.f;  // the near player's panel is at the bottom: up; the rival's at the top: down
					const float Pop = .6f + .4f * YgoEase::Back(YgoEase::Span(T, 0, .25f));
					return FSlateRenderTransform(FScale2D(Pop), FVector2D(0, Dir * (110 + 55 * YgoEase::Out(T))));
				})
			]
		];
}

TSharedRef<SWidget> SYgoHud::PhaseBar()
{
	TSharedRef<SHorizontalBox> Row = SNew(SHorizontalBox);
	Row->AddSlot().AutoWidth().VAlign(VAlign_Center).Padding(4, 0, 14, 0)
	[
		SNew(STextBlock)
		.Font(Display(17))
		.ColorAndOpacity(GoldText)
		.Text_Lambda([this] { const FYgoDuel* D = Duel(); return FText::Format(LOCTEXT("TurnN", "Turno {0}"), D ? D->Turn : 0); })
	];
	for (int32 i = 0; i < 6; ++i)
	{
		// -1 behind us, 0 now, 1 reachable, 2 not this turn (the first has no Battle Phase).
		auto State = [this, i]
		{
			const FYgoDuel* D = Duel();
			const int32 At = D ? PhaseIndex(D->Phase) : -1;
			if (i == At) return 0;
			if (i < At) return -1;
			return D && D->Turn == 1 && (i == PhaseBattle || i == PhaseMain2) ? 2 : 1;
		};
		const TSharedRef<SButton> Tile = SNew(SButton)
			.ButtonStyle(&Plain)
			.ContentPadding(0)
			.IsFocusable(false)  // never disabled: Slate would grey out the gold of the current phase
			.OnClicked_Lambda([this, i, State] { if (Live() && State() == 1) { Sound(EYgoSound::Click); GotoPhase(i); } return FReply::Handled(); });
		const TWeakPtr<SButton> Weak = Tile;
		Tile->SetContent(
			SNew(SYgoPlate)
			.Radius(8).Rim(2.5f).Padding(FMargin(13, 5))
			.Fill_Lambda([State] { return State() == 0 ? YgoPlate::Gold : YgoPlate::Lapis; })
			.Lit_Lambda([this, Weak, State] { const TSharedPtr<SButton> B = Weak.Pin(); return B.IsValid() && B->IsHovered() && Live() && State() == 1 ? .6f : 0.f; })
			.Alpha_Lambda([State] { const int32 S = State(); return S == -1 ? .55f : S == 2 ? .3f : 1.f; })
			[
				SNew(STextBlock)
				.Font(Display(15))
				.Text(FText::FromString(PhaseShort[i]))
				.ColorAndOpacity_Lambda([State] { return FSlateColor(State() == 0 ? Ink : Cream); })
			]);
		Row->AddSlot().AutoWidth().Padding(3, 0)[Tile];
	}
	Row->AddSlot().AutoWidth().VAlign(VAlign_Center).Padding(14, 0, 2, 0)
	[
		Action(LOCTEXT("EndTurn", "Fin de turno"), [this] { EndTurn(); }, TAttribute<bool>::CreateLambda([this] { return Live(); }), 14)
	];
	return SNew(SVerticalBox)
		.Visibility_Lambda([this] { const FYgoDuel* D = Duel(); return D && D->bValid && D->bStarted ? EVisibility::SelfHitTestInvisible : EVisibility::Collapsed; })
		+ SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center)
		[
			SNew(SYgoPlate).Radius(14).Rim(3.5f).Padding(FMargin(16, 8))[Row]
		]
		+ SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center).Padding(0, 7, 0, 0)
		[
			SNew(STextBlock)
			.Font(Reading("Bold", 15))
			.ColorAndOpacity(Cream)
			.ShadowOffset(FVector2D(0, 1)).ShadowColorAndOpacity(FLinearColor(0, 0, 0, .9f))
			.Text(LOCTEXT("PickAttacker", "Toca tu monstruo para atacar"))
			.Visibility_Lambda([this]
			{
				const FYgoDuel* D = Duel();
				return D && D->Phase == TEXT("battle") && !D->bBattlePreview && AttackerId.IsEmpty() ? EVisibility::HitTestInvisible : EVisibility::Collapsed;
			})
		];
}

TSharedRef<SWidget> SYgoHud::StartPanel()
{
	auto Over = [this] { const FYgoDuel* D = Duel(); return D && D->bStarted && !D->Result.IsEmpty(); };
	auto NotYet = [this] { const FYgoDuel* D = Duel(); return D && D->bValid && !D->bStarted; };
	auto Idle = TAttribute<bool>::CreateLambda([this] { return !bBusy; });
	return SNew(SBox)
		.WidthOverride(620)
		.Visibility_Lambda([Over, NotYet] { return Over() || NotYet() ? EVisibility::Visible : EVisibility::Collapsed; })
		[
			SNew(SYgoPlate).Radius(18).Rim(5).Body(.96f).Padding(FMargin(32, 24))
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center)
				[
					SNew(STextBlock)
					.Font(Display(38, TEXT("Black")))
					.ColorAndOpacity(Cream)
					.Text_Lambda([this, Over]
					{
						const FYgoDuel* D = Duel();
						if (!Over() || !D) return LOCTEXT("NewDuel", "Duelo");
						return D->Players.IsValidIndex(D->Winner) ? FText::Format(LOCTEXT("Won", "Gana {0}"), FText::FromString(D->Players[D->Winner].Name)) : LOCTEXT("Draw", "Empate");
					})
				]
				+ SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center).Padding(0, 16, 0, 0)
				[
					SNew(SHorizontalBox)
					.Visibility_Lambda([NotYet] { return NotYet() ? EVisibility::SelfHitTestInvisible : EVisibility::Collapsed; })
					+ SHorizontalBox::Slot().AutoWidth().Padding(5, 0)
					[
						Action(LOCTEXT("StartFirst", "Empieza Jugador 1"), [this] { StartDuel(0); }, Idle, 17)
					]
					+ SHorizontalBox::Slot().AutoWidth().Padding(5, 0)
					[
						Action(LOCTEXT("StartSecond", "Empieza Jugador 2"), [this] { StartDuel(1); }, Idle, 17)
					]
				]
				+ SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center)
				[
					SNew(SBox)
					.Visibility_Lambda([Over] { return Over() ? EVisibility::SelfHitTestInvisible : EVisibility::Collapsed; })
					[
						Action(LOCTEXT("NextDuel", "Nuevo duelo"), [this]
						{
							const TSharedRef<FJsonObject> E = MakeShared<FJsonObject>();
							E->SetStringField(TEXT("type"), TEXT("reset"));
							Send(E);
						}, Idle, 17)
					]
				]
			]
		];
}

TSharedRef<SWidget> SYgoHud::PromptPanel()
{
	return SNew(SBox)
		.WidthOverride(520)
		.Visibility_Lambda([this] { return PromptOpen() ? EVisibility::Visible : EVisibility::Collapsed; })
		[
			SNew(SYgoPlate).Radius(14).Rim(4).Body(.96f).Padding(FMargin(24, 18))
			[
				SAssignNew(PromptBody, SVerticalBox)
			]
		];
}

TSharedRef<SWidget> SYgoHud::PlayPanel()
{
	return SAssignNew(PlayRoot, SBox)
		.MaxDesiredWidth(780)
		.Visibility_Lambda([this] { return Now - PlayAt < PlaySeconds ? EVisibility::Visible : EVisibility::Collapsed; })
		[
			SNew(SYgoPlate).Radius(12).Rim(3).Padding(FMargin(20, 9))
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot().AutoHeight()
				[
					SNew(SHorizontalBox)
					+ SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center)
					[
						SNew(STextBlock).Text_Lambda([this] { return PlayText; }).Font(Reading("Regular", 17)).ColorAndOpacity(Cream).AutoWrapText(true)
					]
					+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(14, 0, 0, 0)
					[
						SAssignNew(PlayActions, SHorizontalBox)
					]
				]
				+ SVerticalBox::Slot().AutoHeight().Padding(0, 3, 0, 0)
				[
					SNew(STextBlock)
					.Text_Lambda([this] { return PlayWarning; })
					.Font(Reading("Regular", 14)).ColorAndOpacity(GoldText).AutoWrapText(true)
					.Visibility_Lambda([this] { return PlayWarning.IsEmpty() ? EVisibility::Collapsed : EVisibility::HitTestInvisible; })
				]
			]
		];
}

const FYgoQuestion* SYgoHud::FindQuestion(const FString& Key) const
{
	const FYgoDuel* D = Duel();
	return D && !Key.IsEmpty() ? D->Questions.FindByPredicate([&](const FYgoQuestion& Q) { return Q.Key == Key; }) : nullptr;
}

bool SYgoHud::PromptOpen() const
{
	const FYgoDuel* D = Duel();
	return D && D->bStarted && (D->bBattlePreview || !AttackerId.IsEmpty() || FindQuestion(AskedKey) != nullptr);
}

const FYgoQuestion* SYgoHud::AskedQuestion() const
{
	const FYgoDuel* D = Duel();
	return D && D->bStarted && !D->bBattlePreview && AttackerId.IsEmpty() ? FindQuestion(AskedKey) : nullptr;
}

void SYgoHud::SelectQuestion()
{
	const FYgoDuel* D = Duel();
	if (!D || D->Questions.IsEmpty()) { AskedKey.Empty(); bListOpen = false; Later.Reset(); return; }
	// A question that went away and comes back is new again.
	for (auto It = Later.CreateIterator(); It; ++It) if (!FindQuestion(*It)) It.RemoveCurrent();
	const FYgoQuestion* Shown = FindQuestion(AskedKey);
	if (Shown && (bListOpen || (Shown->Options.Num() && !Later.Contains(AskedKey)))) return;
	for (const FYgoQuestion& Q : D->Questions)
		if (Q.Options.Num() && !Later.Contains(Q.Key)) { AskedKey = Q.Key; return; }
	if (bListOpen) AskedKey = D->Questions[0].Key;
	else AskedKey.Empty();
}

void SYgoHud::StepQuestion()
{
	const FYgoDuel* D = Duel();
	if (!D || D->Questions.Num() < 2 || !bListOpen) return;
	const int32 At = D->Questions.IndexOfByPredicate([&](const FYgoQuestion& Q) { return Q.Key == AskedKey; });
	AskedKey = D->Questions[(At + 1) % D->Questions.Num()].Key;
}

void SYgoHud::CloseQuestion()
{
	if (!AttackerId.IsEmpty()) { AttackerId.Empty(); return; }
	if (const FYgoDuel* D = Duel()) if (D->bBattlePreview) return;  // an attack is resolved or cancelled, not put off
	if (!AskedKey.IsEmpty()) Later.Add(AskedKey);
	if (bListOpen) { bListOpen = false; if (const FYgoDuel* D = Duel()) for (const FYgoQuestion& Q : D->Questions) Later.Add(Q.Key); }
	AskedKey.Empty();
}

FText SYgoHud::Sentence(const FYgoQuestion& Q) const
{
	const FYgoDuel* D = Duel();
	const FText Who = D && D->Players.IsValidIndex(Q.Player) ? FText::FromString(D->Players[Q.Player].Name) : FText::Format(LOCTEXT("PlayerN", "Jugador {0}"), Q.Player + 1);
	const FText Card = Q.CardName.IsEmpty() ? LOCTEXT("UnknownCard", "Una carta sin identificar") : FText::FromString(Q.CardName);
	const FText Zone = FText::FromString(Q.ZoneLabel);
	if (Q.Kind == TEXT("unexplained")) return FText::Format(LOCTEXT("Unexplained", "{0} apareció en la {1} de {2}."), Card, Zone, Who);
	if (Q.Kind == TEXT("missing")) return FText::Format(LOCTEXT("Missing", "La carta de la {0} de {1} ya no está. ¿A dónde fue?"), Zone, Who);
	if (Q.Kind == TEXT("moved")) return FText::Format(LOCTEXT("Moved", "{0} aparece en la {1} de {2}, pero estaba en otra zona."), Card, Zone, Who);
	if (Q.Kind == TEXT("different_copy")) return FText::Format(LOCTEXT("Different", "En la {0} de {1} hay otra carta distinta de la registrada."), Zone, Who);
	if (Q.Kind == TEXT("conflict"))
		return FText::Format(LOCTEXT("Conflict", "{0} en la {1} de {2}: la cámara ve {3}, el duelo tiene {4}."), Card, Zone, Who, PositionName(Q.Position), PositionName(Q.ExpectedPosition));
	return FText::FromString(Q.ZoneLabel + TEXT(": ") + Q.Kind);
}

void SYgoHud::RebuildPrompt()
{
	if (!PromptBody.IsValid()) return;
	PromptBody->ClearChildren();
	Keyed.Reset();
	const FYgoDuel* D = Duel();
	if (!D) return;
	auto Line = [this](const FText& Text, const FLinearColor& Color, int32 Size, float Top, const char* Style = "Regular")
	{
		PromptBody->AddSlot().AutoHeight().Padding(0, Top, 0, 0)
		[
			SNew(STextBlock).Text(Text).AutoWrapText(true).Font(Reading(Style, Size)).ColorAndOpacity(Color)
		];
	};
	// The choices carry the digit that plays them; a keyed choice obeys the same rule as its button.
	TSharedRef<SWrapBox> Choices = SNew(SWrapBox).UseAllottedSize(true).InnerSlotPadding(FVector2D(8, 8));
	auto Choice = [this, &Choices](const FText& Label, TFunction<void()> Do, TFunction<bool()> Allowed)
	{
		Keyed.Add([this, Do, Allowed] { if (Allowed()) { Sound(EYgoSound::Click); Do(); } });
		Choices->AddSlot()
		[
			Action(FText::Format(LOCTEXT("Keyed", "{0}   {1}"), Keyed.Num(), Label), Do, TAttribute<bool>::CreateLambda([Allowed] { return Allowed(); }))
		];
	};
	auto CanAct = [this] { return Live(); };

	if (D->bBattlePreview)
	{
		const bool bProblem = !D->BattleProblem.IsEmpty();
		Line(FText::FromString(D->BattleText), Cream, 19, 0, "Bold");
		Line(bProblem ? FText::Format(LOCTEXT("BattleProblem", "No se puede calcular: {0}"), FText::FromString(D->BattleProblem))
			: FText::Format(LOCTEXT("BattleOutcome", "Resultado: {0}."), FText::FromString(D->BattleOutcome)), bProblem ? Hurt : GoldText, 16, 6);
		Choice(LOCTEXT("ApplyBattle", "Aplicar"), [this]
		{
			const TSharedRef<FJsonObject> E = MakeShared<FJsonObject>();
			E->SetStringField(TEXT("type"), TEXT("resolve_battle"));
			Send(E);
		}, [this, bProblem] { return Live() && !bProblem; });
		Choice(LOCTEXT("CancelBattle", "Cancelar"), [this]
		{
			const TSharedRef<FJsonObject> E = MakeShared<FJsonObject>();
			E->SetStringField(TEXT("type"), TEXT("cancel_attack"));
			Send(E);
		}, CanAct);
		PromptBody->AddSlot().AutoHeight().Padding(0, 14, 0, 0)[Choices];
		return;
	}

	if (!AttackerId.IsEmpty())
	{
		const FYgoBoardCard* Card = D->Board.FindByPredicate([&](const FYgoBoardCard& C) { return C.CopyId == AttackerId; });
		Line(FText::Format(LOCTEXT("Attacking", "{0} va a atacar."), Card && !Card->Name.IsEmpty() ? FText::FromString(Card->Name) : LOCTEXT("Monster", "Tu monstruo")), Cream, 19, 0, "Bold");
		Line(LOCTEXT("PickTarget", "Toca al monstruo rival, o ataca directamente."), Muted, 15, 6);
		Choice(LOCTEXT("DirectAttack", "Ataque directo"), [this] { Attack(nullptr); }, CanAct);
		Choice(LOCTEXT("CancelAttacker", "Cancelar"), [this] { AttackerId.Empty(); }, CanAct);
		PromptBody->AddSlot().AutoHeight().Padding(0, 14, 0, 0)[Choices];
		return;
	}

	const FYgoQuestion* Q = FindQuestion(AskedKey);
	if (!Q) return;
	Line(Sentence(*Q), Cream, 19, 0, "Bold");
	if (!Q->Hint.IsEmpty()) Line(FText::FromString(Q->Hint), Muted, 15, 6);

	// Level 5+ Normal Summons need tributes: the player's own monsters on the field.
	const FString Self = IdOf(Q->CopyId);
	if (Q->Kind == TEXT("unexplained") && Q->Level >= 5)
	{
		TSharedRef<SWrapBox> Chips = SNew(SWrapBox).UseAllottedSize(true).InnerSlotPadding(FVector2D(6, 6));
		int32 Chosen = 0;
		for (const FYgoBoardCard& C : D->Board)
		{
			if (C.Player != Q->Player || !C.Zone.Contains(TEXT("monster")) || C.CopyId == Self) continue;
			++Chosen;
			const FString Id = C.CopyId;
			Chips->AddSlot()
			[
				Action(C.Name.IsEmpty() ? LOCTEXT("FacedownTribute", "Boca abajo") : FText::FromString(C.Name),
					[this, Id] { if (Tributes.Remove(Id) == 0) Tributes.Add(Id); },
					TAttribute<bool>::CreateLambda([CanAct] { return CanAct(); }), 13,
					TAttribute<bool>::CreateLambda([this, Id] { return Tributes.Contains(Id); }))
			];
		}
		if (Chosen)
		{
			Line(FText::Format(LOCTEXT("TributeHelp", "Nivel {0}: marca los monstruos sacrificados si fue Invocación Normal o colocación."), Q->Level), Muted, 15, 8);
			PromptBody->AddSlot().AutoHeight().Padding(0, 6, 0, 0)[Chips];
		}
	}
	const FString Key = Q->Key;
	for (const FYgoOption& O : Q->Options)
	{
		Choice(FText::FromString(O.Label), [this, Key, O]
		{
			if (const FYgoQuestion* Now = FindQuestion(Key)) Answer(*Now, O);
		}, CanAct);
	}
	if (Q->Options.Num()) PromptBody->AddSlot().AutoHeight().Padding(0, 14, 0, 0)[Choices];

	// Nothing here is forced: a question waits, and the player can read the others.
	const int32 Total = D->Questions.Num();
	const int32 At = D->Questions.IndexOfByPredicate([&](const FYgoQuestion& Item) { return Item.Key == Key; });
	TSharedRef<SHorizontalBox> Footer = SNew(SHorizontalBox);
	Footer->AddSlot().FillWidth(1).VAlign(VAlign_Center)
	[
		SNew(STextBlock)
		.Font(Display(14)).ColorAndOpacity(GoldText)
		.Text(Total > 1 ? FText::Format(LOCTEXT("OfTotal", "{0} de {1}"), At + 1, Total) : FText::GetEmpty())
	];
	if (bListOpen && Total > 1)
		Footer->AddSlot().AutoWidth().Padding(0, 0, 8, 0)[Action(LOCTEXT("NextQuestion", "Siguiente"), [this] { StepQuestion(); }, true, 13)];
	Footer->AddSlot().AutoWidth()[Action(Q->Options.Num() ? LOCTEXT("Later", "Luego") : LOCTEXT("Close", "Cerrar"), [this] { CloseQuestion(); }, true, 13)];
	PromptBody->AddSlot().AutoHeight().Padding(0, 12, 0, 0)[Footer];
}

void SYgoHud::RebuildPlay(const FYgoPlay& Play)
{
	PlayText = FText::FromString(Play.Text);
	PlayWarning = Play.Warnings.Num() ? FText::FromString(FString::Join(Play.Warnings, TEXT(" · "))) : FText::GetEmpty();
	PlayActions->ClearChildren();
	const FString Id = Play.Id;
	auto CanAct = TAttribute<bool>::CreateLambda([this] { return Live(); });
	for (const FYgoOption& A : Play.Alternatives)
	{
		const FString Type = A.Type;
		PlayActions->AddSlot().AutoWidth().Padding(6, 0, 0, 0)
		[
			Action(FText::Format(LOCTEXT("WasInstead", "Era: {0}"), FText::FromString(A.Label)), [this, Id, Type] { Revise(Id, Type); }, CanAct, 13)
		];
	}
	UndoPlay = [this, Id] { Revise(Id, FString()); };
	PlayActions->AddSlot().AutoWidth().Padding(6, 0, 0, 0)
	[
		Action(LOCTEXT("Undo", "Deshacer"), UndoPlay, CanAct, 13)
	];
}

void SYgoHud::Send(const TSharedRef<FJsonObject>& Event)
{
	UYgoLab* L = Lab.Get();
	if (!L || bBusy) return;
	bBusy = true;  // the answer is only done when the lab says so
	const TWeakPtr<SYgoHud> Weak = SharedThis(this);
	L->Act(Event, [Weak](const FString& Error)
	{
		const TSharedPtr<SYgoHud> Self = Weak.Pin();
		if (!Self.IsValid()) return;
		Self->bBusy = false;
		if (Error.IsEmpty()) { Self->ErrorAt = -100; Self->Tributes.Reset(); return; }
		Self->ErrorText = FText::FromString(Error);
		Self->bErrorIsNote = false;
		Self->ErrorAt = Self->Now;
		Self->Sound(EYgoSound::Fail);
	});
}

void SYgoHud::Sound(EYgoSound Which, float Volume) const
{
	if (UYgoFeel* F = Feel.Get()) F->Play(Which, Volume);
}

void SYgoHud::Note(const FText& Text)
{
	ErrorText = Text; bErrorIsNote = true; ErrorAt = Now;
}

void SYgoHud::PickCard(const FString& CopyId)
{
	const FYgoDuel* D = Duel();
	if (!Live() || !D || D->Phase != TEXT("battle") || D->bBattlePreview) return;
	const FYgoBoardCard* Card = D->Board.FindByPredicate([&](const FYgoBoardCard& C) { return C.CopyId == CopyId; });
	if (!Card || !Card->Zone.Contains(TEXT("monster"))) return;
	if (Card->Player == D->Current && Card->Position == TEXT("attack")) { AttackerId = CopyId; Sound(EYgoSound::Click); }
	else if (Card->Player != D->Current && !AttackerId.IsEmpty()) { Sound(EYgoSound::Click); Attack(Card->RawCopyId); }
}

void SYgoHud::Attack(const TSharedPtr<FJsonValue>& Target)
{
	const FYgoDuel* D = Duel();
	const FYgoBoardCard* Card = D ? D->Board.FindByPredicate([&](const FYgoBoardCard& C) { return C.CopyId == AttackerId; }) : nullptr;
	if (!Card) { AttackerId.Empty(); return; }
	const TSharedRef<FJsonObject> E = MakeShared<FJsonObject>();
	E->SetStringField(TEXT("type"), TEXT("attack"));
	SetId(E, TEXT("attacker"), Card->RawCopyId);
	SetId(E, TEXT("target"), Target);
	AttackerId.Empty();
	Send(E);
}

void SYgoHud::StartDuel(int32 Starting)
{
	const TSharedRef<FJsonObject> E = MakeShared<FJsonObject>();
	E->SetStringField(TEXT("type"), TEXT("start_duel"));
	E->SetArrayField(TEXT("names"), {MakeShared<FJsonValueString>(TEXT("Jugador 1")), MakeShared<FJsonValueString>(TEXT("Jugador 2"))});
	E->SetNumberField(TEXT("starting"), Starting);
	E->SetArrayField(TEXT("extra_deck_sizes"), {MakeShared<FJsonValueNumber>(15), MakeShared<FJsonValueNumber>(15)});
	Send(E);
}

void SYgoHud::GotoPhase(int32 Phase)
{
	const TSharedRef<FJsonObject> E = MakeShared<FJsonObject>();
	E->SetStringField(TEXT("type"), TEXT("goto_phase"));
	E->SetStringField(TEXT("phase"), PhaseKeys[Phase]);
	Send(E);
}

void SYgoHud::EndTurn()
{
	const TSharedRef<FJsonObject> E = MakeShared<FJsonObject>();
	E->SetStringField(TEXT("type"), TEXT("end_turn"));
	Send(E);
}

void SYgoHud::NextPhase()
{
	const FYgoDuel* D = Duel();
	if (!Live() || !D) return;
	const int32 At = PhaseIndex(D->Phase);
	if (At < 0) return;
	if (At == PhaseEnd) { EndTurn(); return; }
	const int32 Next = D->Turn == 1 && At + 1 == PhaseBattle ? PhaseEnd : At + 1;
	GotoPhase(Next);
}

void SYgoHud::Answer(const FYgoQuestion& Q, const FYgoOption& Option)
{
	if (!Live()) return;
	const TSharedRef<FJsonObject> E = MakeShared<FJsonObject>();
	E->SetStringField(TEXT("type"), Option.Type);
	E->SetNumberField(TEXT("player"), Q.Player);
	if (Q.Kind == TEXT("missing")) SetId(E, TEXT("copy_id"), Q.ExpectedCopy);
	else if (Option.Type == TEXT("change_position")) { SetId(E, TEXT("copy_id"), Q.CopyId); E->SetStringField(TEXT("position"), Q.Position); }
	else if (Option.Type == TEXT("flip")) SetId(E, TEXT("copy_id"), Q.CopyId);
	else
	{
		E->SetStringField(TEXT("zone"), Q.Zone);
		SetId(E, TEXT("copy_id"), Q.CopyId);
		if (!Q.CardId.IsEmpty()) E->SetStringField(TEXT("card_id"), Q.CardId);
	}
	if (Option.Type == TEXT("normal_summon") || Option.Type == TEXT("set_monster"))
	{
		TArray<TSharedPtr<FJsonValue>> Chosen;
		if (const FYgoDuel* D = Duel())
			for (const FYgoBoardCard& C : D->Board) if (Tributes.Contains(C.CopyId) && C.RawCopyId.IsValid()) Chosen.Add(C.RawCopyId);
		E->SetArrayField(TEXT("tributes"), Chosen);
	}
	if (Option.Type == TEXT("special_summon") && (Q.Position == TEXT("attack") || Q.Position == TEXT("defense")))
		E->SetStringField(TEXT("position"), Q.Position);
	Send(E);
}

void SYgoHud::Revise(const FString& Id, const FString& Replacement)
{
	const TSharedRef<FJsonObject> E = MakeShared<FJsonObject>();
	E->SetStringField(TEXT("type"), TEXT("revise"));
	E->SetStringField(TEXT("id"), Id);
	if (!Replacement.IsEmpty()) E->SetStringField(TEXT("replacement"), Replacement);
	Send(E);
}

FReply SYgoHud::OnKeyDown(const FGeometry& Geometry, const FKeyEvent& Event)
{
	static const FKey Digits[] = {EKeys::One, EKeys::Two, EKeys::Three, EKeys::Four, EKeys::Five, EKeys::Six, EKeys::Seven, EKeys::Eight, EKeys::Nine};
	static const FKey Pad[] = {EKeys::NumPadOne, EKeys::NumPadTwo, EKeys::NumPadThree, EKeys::NumPadFour, EKeys::NumPadFive, EKeys::NumPadSix, EKeys::NumPadSeven, EKeys::NumPadEight, EKeys::NumPadNine};
	const FKey Key = Event.GetKey();
	for (int32 i = 0; i < 9; ++i)
		if (Key == Digits[i] || Key == Pad[i])
		{
			if (PromptOpen() && Keyed.IsValidIndex(i)) { const TFunction<void()> Do = Keyed[i]; Do(); }
			return FReply::Handled();
		}
	if (Key == EKeys::SpaceBar) { NextPhase(); return FReply::Handled(); }
	if (Key == EKeys::Tab) { bListOpen = true; StepQuestion(); return FReply::Handled(); }
	if (Key == EKeys::Escape) { CloseQuestion(); return FReply::Handled(); }
	if (Key == EKeys::G) { bZones = !bZones; return FReply::Handled(); }
	if (Key == EKeys::M)
	{
		if (UYgoFeel* F = Feel.Get()) { F->ToggleMute(); Note(F->IsMuted() ? LOCTEXT("Muted", "Sonido apagado") : LOCTEXT("Unmuted", "Sonido encendido")); }
		return FReply::Handled();
	}
	if (Key == EKeys::C)
	{
		if (UYgoFeel* F = Feel.Get()) { F->ToggleCalm(); Note(F->IsCalm() ? LOCTEXT("Calm", "Modo tranquilo: sin sacudidas ni destellos") : LOCTEXT("Lively", "Sacudidas y destellos activos")); }
		return FReply::Handled();
	}
	if (Key == EKeys::Z)
	{
		if (UndoPlay && Now - PlayAt < PlaySeconds && Live()) UndoPlay();  // only a play the player can see
		return FReply::Handled();
	}
	return SCompoundWidget::OnKeyDown(Geometry, Event);
}

void SYgoHud::ShowBanner(const FText& Title, const FText& Subtitle, const FLinearColor& InAccent)
{
	BannerTitle = Title; BannerSubtitle = Subtitle; BannerAccent = InAccent; BannerAt = Now;
}

void SYgoHud::Flash(const FLinearColor& Color, float Alpha, float Seconds)
{
	FlashColor = Color; FlashAlpha = Alpha; FlashSeconds = FMath::Max(Seconds, .01f); FlashAt = Now;
}

void SYgoHud::PreviewLp(int32 Player, int32 Delta)
{
	if (Player < 0 || Player > 1) return;
	LpChangedAt[Player] = Now; bLpHurt[Player] = Delta < 0; LpDelta[Player] = Delta;
}

void SYgoHud::Tick(const FGeometry& Geometry, const double CurrentTime, const float DeltaTime)
{
	SCompoundWidget::Tick(Geometry, CurrentTime, DeltaTime);
	Now = CurrentTime;
	if (const FYgoDuel* D = Duel())
	{
		for (int32 i = 0; i < 2 && i < D->Players.Num(); ++i)
		{
			const int32 Lp = D->Players[i].Lp;
			if (LastLp[i] >= 0 && Lp != LastLp[i]) { LpChangedAt[i] = Now; bLpHurt[i] = Lp < LastLp[i]; LpDelta[i] = Lp - LastLp[i]; }
			if (LastLp[i] < 0) ShownLp[i] = Lp;  // first state: no count from 8000
			LastLp[i] = Lp;
			// Count toward the new value, fast at first (the 2D HUD: 8 % of the gap per frame at 60 fps).
			ShownLp[i] += (Lp - ShownLp[i]) * FMath::Min(1.f, DeltaTime * 5.f);
			if (FMath::Abs(Lp - ShownLp[i]) < 1.f) ShownLp[i] = Lp;
			else if (Now >= TickAt) { TickAt = Now + .05; Sound(EYgoSound::Tick); }
		}
		if (D->Phase != TEXT("battle") || !D->Board.ContainsByPredicate([this](const FYgoBoardCard& C) { return C.CopyId == AttackerId; })) AttackerId.Empty();
		if (D->Recent.Num())
		{
			const FYgoPlay& Last = D->Recent[0];
			if (Last.Id != LastPlayId)
			{
				if (!LastPlayId.IsEmpty() || Now > 3) { RebuildPlay(Last); PlayAt = Now; }
				LastPlayId = Last.Id;
			}
		}
		SelectQuestion();
		// The prompt is rebuilt only when what it shows changes: it would lose the pointer otherwise.
		FString Key;
		if (D->bBattlePreview) Key = TEXT("battle|") + D->BattleText + D->BattleOutcome + D->BattleProblem;
		else if (!AttackerId.IsEmpty()) Key = TEXT("attacker|") + AttackerId;
		else if (const FYgoQuestion* Q = FindQuestion(AskedKey))
		{
			Key = FString::Printf(TEXT("%s|%s|%s|%s|%d|%d|%d|%d"), *Q->Key, *Q->Kind, *Q->CardName, *Q->Position, Q->Level, D->Questions.Num(), D->Board.Num(), bListOpen);
			for (const FYgoOption& O : Q->Options) Key += O.Type;
		}
		if (Key != PromptKey) { PromptKey = Key; RebuildPrompt(); }
		const bool bOpen = PromptOpen();
		if (bOpen && !bWasOpen) Sound(EYgoSound::Ask);
		bWasOpen = bOpen;
	}
	// Reading or about to correct the last play keeps it up.
	if (PlayRoot.IsValid())
	{
		if (PlayRoot->IsHovered()) PlayAt = FMath::Max(PlayAt, Now - PlaySeconds + 1.5);
		const float Age = Now - PlayAt;
		PlayRoot->SetRenderOpacity(YgoEase::Span(Age, 0, .2f) * (1 - YgoEase::Span(Age, PlaySeconds - .6f, PlaySeconds)));
	}
	// Banner: pops in with an overshoot, holds, fades.
	const float Age = Now - BannerAt;
	const float Opacity = YgoEase::Span(Age, 0, .15f) * (1 - YgoEase::Span(Age, 1.7f, 2.3f));
	Banner->SetVisibility(Opacity > 0 ? EVisibility::HitTestInvisible : EVisibility::Collapsed);
	Banner->SetRenderOpacity(Opacity);
	Banner->SetRenderTransform(FSlateRenderTransform(.82f + .18f * YgoEase::Back(YgoEase::Span(Age, 0, .4f))));
	// A click on the video hands the keyboard to the game's viewport, where nothing listens.
	if (FSlateApplication::IsInitialized())
	{
		const TSharedPtr<SWidget> Focused = FSlateApplication::Get().GetKeyboardFocusedWidget();
		if (!Focused.IsValid() || Focused->GetTypeAsString().Contains(TEXT("Viewport"))) FSlateApplication::Get().SetKeyboardFocus(SharedThis(this), EFocusCause::SetDirectly);
	}
}

#undef LOCTEXT_NAMESPACE
