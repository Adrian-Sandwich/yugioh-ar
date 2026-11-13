#include "YgoStage.h"

#include "Camera/CameraComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/Texture2D.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "HAL/PlatformMisc.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Misc/CommandLine.h"
#include "Misc/Paths.h"
#include "ProceduralMeshComponent.h"
#include "UnrealClient.h"
#include "YgoEase.h"
#include "YgoFeel.h"
#include "YgoFx.h"
#include "YgoHud.h"
#include "YgoLab.h"
#include "YgoParticles.h"
#include "YgoShatterFx.h"
#include "YgoSummonFx.h"
#include "YgoTableView.h"

#define LOCTEXT_NAMESPACE "YgoStage"

namespace
{
	constexpr double ArrivalMemory = 15.0;  // s: the same card back in the same zone is not a new arrival
	constexpr double StartupGrace = 2.5;    // s: cards already on the table appear without an entrance
	constexpr double FigureHold = .6;       // s a figure outlives its track (a hand passing over the card)
	constexpr double BackHold = 1.5;        // s a face-down figure outlives its back (the duel comes every 0.5 s)
	constexpr float SpritePad = 1.12f;      // the sprite's quad around the cut-out, room for its halo (M_FxSprite)
	constexpr float AttackDuration = 1.35f; // 2D: 0.9 s; the blow lands at 42 %
	constexpr float OnPlane = .44f;         // card widths in one of the 2D view's plane units
	const FLinearColor Fire = FLinearColor::FromSRGBColor(FColor(255, 150, 60));      // web/duel.js RGB.fire
	const FLinearColor BackGlow = FLinearColor::FromSRGBColor(FColor(255, 160, 70));  // RGB.back
	const TCHAR* ShieldFront = TEXT("/fx/shield-millennium-front.png");
	const TCHAR* ShieldBack = TEXT("/fx/shield-millennium-back.png");
	// Their relief (tools/make_shield_relief.py): normal x and y, how metallic, and height in alpha.
	const TCHAR* ShieldFrontRelief = TEXT("/fx/shield-millennium-front-relief.png");
	const TCHAR* ShieldBackRelief = TEXT("/fx/shield-millennium-back-relief.png");

	// The shield as a solid, in the engine plane's units (100 x 100 across X and Y, front toward +Z;
	// Z in the same units as Y): a face per side, each raised by its relief, and the edge between them.
	// One vertex per ShieldStep pixels of the front relief, whose alpha is also the silhouette.
	// Vertex colour for M_FxMetal: red on the edge, green on the back face.
	struct FShieldMesh
	{
		TArray<FVector> Vertices;
		TArray<int32> Triangles;
		TArray<FVector2D> UVs;
		TArray<FLinearColor> Colors;
	};
	constexpr int32 ShieldStep = 2;
	constexpr float ShieldRim = 1.7f;         // half the thickness at the edge
	constexpr float ShieldFrontDepth = 5.f;   // a height of 1 on the front (make_shield_relief.py DEPTH_PX)
	constexpr float ShieldBackDepth = 2.5f;

	const FShieldMesh& ShieldMesh(const FYgoPixels& Front, const FYgoPixels& Rear)
	{
		static FShieldMesh M;
		if (M.Vertices.Num()) return M;
		const int32 S = ShieldStep, NX = Front.Width / S, NY = Front.Height / S, Row = NX + 1;
		auto Inside = [&](int32 I, int32 J) { return I >= 0 && J >= 0 && I < NX && J < NY && Front.At(I * S + S / 2, J * S + S / 2, 3) > 0; };
		// Height at a lattice corner: the mean of the pixels around it.
		auto Mean = [](const FYgoPixels& P, int32 X, int32 Y) { return (P.At(X - 1, Y - 1, 3) + P.At(X, Y - 1, 3) + P.At(X - 1, Y, 3) + P.At(X, Y, 3)) / 4; };
		// Where each lattice corner sits, in cells. The silhouette follows pixels, so its corners are
		// eased toward their neighbours along it: an edge that curves instead of climbing in steps.
		static const int32 Edges[4][6] = {  // neighbour (dx, dy), and the two corners of the side they share
			{0, -1, 0, 0, 1, 0}, {1, 0, 1, 0, 1, 1}, {0, 1, 1, 1, 0, 1}, {-1, 0, 0, 1, 0, 0}};
		TArray<FVector2f> At;
		At.SetNumUninitialized(Row * (NY + 1));
		for (int32 J = 0; J <= NY; ++J) for (int32 I = 0; I <= NX; ++I) At[J * Row + I] = FVector2f(I, J);
		TArray<TPair<int32, int32>> Outline;
		for (int32 J = 0; J < NY; ++J)
			for (int32 I = 0; I < NX; ++I)
				if (Inside(I, J))
					for (const int32* E : Edges)
						if (!Inside(I + E[0], J + E[1])) Outline.Emplace((J + E[3]) * Row + I + E[2], (J + E[5]) * Row + I + E[4]);
		for (int32 Pass = 0; Pass < 4; ++Pass)
		{
			TMap<int32, TPair<FVector2f, int32>> Sum;
			for (const TPair<int32, int32>& E : Outline)
			{
				TPair<FVector2f, int32>& A = Sum.FindOrAdd(E.Key, {FVector2f::ZeroVector, 0}); A.Key += At[E.Value]; ++A.Value;
				TPair<FVector2f, int32>& B = Sum.FindOrAdd(E.Value, {FVector2f::ZeroVector, 0}); B.Key += At[E.Key]; ++B.Value;
			}
			for (const TPair<int32, TPair<FVector2f, int32>>& S2 : Sum) At[S2.Key] = (At[S2.Key] + S2.Value.Key / S2.Value.Value) / 2;
		}
		auto Place = [&](int32 I, int32 J, bool bRear)
		{
			const float U = At[J * Row + I].X / NX, V = At[J * Row + I].Y / NY;
			// The back's drawing is read mirrored, so it shows the right way round from behind.
			const float Z = bRear ? -(ShieldRim + ShieldBackDepth * Mean(Rear, FMath::RoundToInt32((1 - U) * Rear.Width), FMath::RoundToInt32(V * Rear.Height)))
				: ShieldRim + ShieldFrontDepth * Mean(Front, I * S, J * S);
			return FVector((U - .5f) * 100, (V - .5f) * 100, Z);
		};
		TArray<int32> Index[4];  // front, back, edge at the front, edge at the back: by lattice corner
		for (TArray<int32>& A : Index) A.Init(-1, Row * (NY + 1));
		auto Vertex = [&](int32 Kind, int32 I, int32 J)
		{
			int32& Slot = Index[Kind][J * Row + I];
			if (Slot < 0)
			{
				Slot = M.Vertices.Add(Place(I, J, Kind == 1 || Kind == 3));
				M.UVs.Add(FVector2D(At[J * Row + I].X / NX, At[J * Row + I].Y / NY));
				M.Colors.Add(FLinearColor(Kind >= 2 ? 1 : 0, Kind == 1 ? 1 : 0, 0, 1));
			}
			return Slot;
		};
		auto Quad = [&](int32 A, int32 B, int32 C, int32 D) { M.Triangles.Append({A, B, C, A, C, D}); };
		for (int32 J = 0; J < NY; ++J)
			for (int32 I = 0; I < NX; ++I)
			{
				if (!Inside(I, J)) continue;
				Quad(Vertex(0, I, J), Vertex(0, I + 1, J), Vertex(0, I + 1, J + 1), Vertex(0, I, J + 1));
				Quad(Vertex(1, I, J), Vertex(1, I, J + 1), Vertex(1, I + 1, J + 1), Vertex(1, I + 1, J));
				for (const int32* E : Edges)
				{
					if (Inside(I + E[0], J + E[1])) continue;
					Quad(Vertex(2, I + E[2], J + E[3]), Vertex(2, I + E[4], J + E[5]), Vertex(3, I + E[4], J + E[5]), Vertex(3, I + E[2], J + E[3]));
				}
			}
		return M;
	}

	UStaticMesh* PlaneMesh() { return LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Plane.Plane")); }
	void Param(UMaterialInstanceDynamic* M, const TCHAR* Name, float Value) { if (M) M->SetScalarParameterValue(Name, Value); }
	// A plane lying on the table at Centre, Radius cm from its centre to its edge.
	void Lay(UStaticMeshComponent* C, const FVector& Centre, float Radius, float Height)
	{
		C->SetWorldLocationAndRotation(Centre + FVector(0, 0, Height), FRotator::ZeroRotator);
		C->SetWorldScale3D(FVector(Radius * 2 / 100.f));
	}
}

AYgoStage::AYgoStage()
{
	PrimaryActorTick.bCanEverTick = true;
	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
	Particles = CreateDefaultSubobject<UYgoParticles>(TEXT("Particles"));
	Particles->SetupAttachment(GetRootComponent());
	Particles->TranslucencySortPriority = 6;
}

void AYgoStage::Setup(AYgoTableView* InView, TSharedPtr<SYgoHud> InHud)
{
	View = InView; Hud = InHud;
	if (UYgoLab* Lab = UYgoLab::Get(this))
	{
		Lab->OnFrame.AddUObject(this, &AYgoStage::OnFrame);
		Lab->OnDuel.AddUObject(this, &AYgoStage::OnDuel);
	}
	if (UMaterialInterface* Metal = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/YgoAR/M_FxMetal.M_FxMetal")))
	{
		Warm = NewObject<UProceduralMeshComponent>(this);
		Warm->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Warm->CastShadow = false;
		Warm->SetupAttachment(GetRootComponent());
		Warm->RegisterComponent();
		Warm->CreateMeshSection_LinearColor(0, {FVector(0, 0, 0), FVector(1, 0, 0), FVector(0, 1, 0)}, {0, 1, 2}, TArray<FVector>(),
			{FVector2D(0, 0), FVector2D(1, 0), FVector2D(0, 1)}, {FLinearColor::Black, FLinearColor::Black, FLinearColor::Black}, TArray<FProcMeshTangent>(), false);
		Warm->SetMaterial(0, Metal);
		Warm->SetWorldScale3D(FVector(1e-3f));
	}
	FParse::Value(FCommandLine::Get(), TEXT("YgoReplay="), ReplayAt);
	FParse::Value(FCommandLine::Get(), TEXT("YgoDemo="), DemoAt);
	FParse::Value(FCommandLine::Get(), TEXT("YgoQuitAfter="), QuitAfter);
	if (FParse::Value(FCommandLine::Get(), TEXT("YgoShots="), ShotDir))
	{
		ShotEvery = .5f;
		FParse::Value(FCommandLine::Get(), TEXT("YgoShotEvery="), ShotEvery);
		ShotDir = FPaths::ConvertRelativePathToFull(ShotDir);
	}
}

double AYgoStage::Clock() const
{
	UYgoFeel* Feel = UYgoFeel::Get(this);
	return Feel ? Feel->Seconds() : FPlatformTime::Seconds();
}

FLinearColor AYgoStage::OwnerColor(const FString& Kind, bool bRival) const
{
	// web/duel.js RGB: monster, rival, spell, trap (sRGB) -> linear.
	if (Kind == TEXT("spell")) return FLinearColor::FromSRGBColor(FColor(63, 230, 164));
	if (Kind == TEXT("trap")) return FLinearColor::FromSRGBColor(FColor(255, 86, 160));
	return bRival ? FLinearColor::FromSRGBColor(FColor(255, 196, 92)) : FLinearColor::FromSRGBColor(FColor(95, 242, 255));
}

bool AYgoStage::PlaceOf(const FYgoTrack& Track, FPlace& Out) const
{
	const UYgoLab* Lab = UYgoLab::Get(this);
	if (!Lab) return false;
	const FYgoScene& S = Lab->GetScene();
	FVector2D C[4];
	for (int32 i = 0; i < 4; ++i) if (!S.ImageToTable(Track.Corners[i], C[i])) return false;
	Out.Centre = (C[0] + C[1] + C[2] + C[3]) / 4;
	Out.Width = .5f * (FVector2D::Distance(C[0], C[1]) + FVector2D::Distance(C[3], C[2]));
	// The image's "down" on the table: where the pixel below the card's centre lands.
	FVector2D Below;
	const FVector2D Pixel = Track.Center();
	if (S.ImageToTable(Pixel + FVector2D(0, 40), Below) && !(Below - Out.Centre).IsNearlyZero())
		Out.Down = (Below - Out.Centre).GetSafeNormal();
	return Out.Width > 5.f;
}

FString AYgoStage::KindOf(const FYgoTrack& Track)
{
	UYgoLab* Lab = UYgoLab::Get(this);
	const FString Type = Lab ? Lab->CardType(Track.CardId) : FString(TEXT("?"));
	if (Type == TEXT("monster") || Type == TEXT("spell") || Type == TEXT("trap")) return Type;
	if (Type.IsEmpty()) return Type;
	// The sheet cannot say: as web/duel.js kindOf, the duel's line for the card, then its zone.
	if (Lab)
		for (const FYgoBoardCard& C : Lab->GetDuel().Board)
			if (C.CopyId == Track.TrackId)
			{
				if (C.Type.StartsWith(TEXT("Trampa"))) return TEXT("trap");
				if (C.Type.StartsWith(TEXT("Magia")) || C.Zone.StartsWith(TEXT("spell:")) || C.Zone == TEXT("field")) return TEXT("spell");
			}
	return TEXT("monster");
}

void AYgoStage::OnFrame()
{
	UYgoLab* Lab = UYgoLab::Get(this);
	if (!Lab) return;
	const double Now = FPlatformTime::Seconds();
	for (const FYgoTrack& T : Lab->GetTracks())
	{
		if (!T.bStable || T.CardId.IsEmpty() || Now < Shattered.FindRef(T.TrackId)) continue;
		FPlace Place;
		if (!PlaceOf(T, Place)) continue;
		const FString Kind = KindOf(T);
		if (Kind.IsEmpty()) continue;  // its sheet is on the way: no entrance as the wrong kind
		const FYgoZone* Zone = Lab->GetScene().ZoneAt(Place.Centre);
		// Arrivals: a card new in its zone (web/duel.js noticeArrivals).
		const FString Key = (Zone ? FString::Printf(TEXT("%d|%s"), Zone->Player, *Zone->Zone) : FString(TEXT("?"))) + TEXT("|") + T.CardId;
		const double* Last = Arrived.Find(Key);
		const bool bNew = (!Last || Now - *Last >= ArrivalMemory) && StartedAt > 0 && Now - StartedAt >= StartupGrace;
		Arrived.Add(Key, Now);
		FFigure& F = FigureFor(T);
		F.Track = T; F.Kind = Kind; F.Target = Place; F.LastSeen = Now; F.bRival = Zone && Zone->Player == 1;
		if (bNew) Arrive(T, Place, Kind, Zone ? Zone->Player : 0);
	}
}

void AYgoStage::Arrive(const FYgoTrack& Track, const FPlace& Place, const FString& Kind, int32 Player)
{
	UYgoLab* Lab = UYgoLab::Get(this);
	UE_LOG(LogTemp, Display, TEXT("YgoAR: entrada de %s (%s)"), *Track.Name, *Kind);
	const FLinearColor Color = OwnerColor(Kind, Player == 1);
	const FVector Where = FYgoScene::TableToUnreal(Place.Centre);
	const double Now = Clock();
	FFigure* F = Figures.Find(Track.TrackId);
	if (UYgoFeel* Feel = UYgoFeel::Get(this)) Feel->Play(EYgoSound::Card);
	FText Subtitle;
	if (Kind == TEXT("monster"))
	{
		if (AYgoSummonFx* Fx = GetWorld()->SpawnActor<AYgoSummonFx>()) Fx->Start(Where, Place.Width / 10.f, Color, View.Get(), Particles);
		if (F) F->SummonAt = Now;
		Subtitle = LOCTEXT("Summon", "INVOCACIÓN");
	}
	else
	{
		const bool bTrap = Kind == TEXT("trap");
		if (AYgoFx* Fx = GetWorld()->SpawnActor<AYgoFx>())
			Fx->Start(bTrap ? EYgoFx::Trap : EYgoFx::Spell, Where, Place.Width / 10.f, Color, View.Get(), Particles, Hud);
		if (F) F->ActivateAt = Now;
		Subtitle = bTrap ? LOCTEXT("Trap", "TRAMPA") : LOCTEXT("Spell", "MAGIA");
	}
	if (Hud.IsValid())
	{
		FString Name = Track.Name;
		if (Name.IsEmpty() && Lab) Name = Lab->CardName(Track.CardId);
		Hud->ShowBanner(FText::FromString(Name), Subtitle, Color);
	}
}

void AYgoStage::OnDuel()
{
	UYgoLab* Lab = UYgoLab::Get(this);
	if (!Lab) return;
	const FYgoDuel& Next = Lab->GetDuel();
	const double Now = FPlatformTime::Seconds();
	// Effects come from what changed in the duel (web/duel.js stageEvents), never from the camera alone.
	if (Prev.bValid && Prev.bStarted && Next.bValid && Next.bStarted)
	{
		const bool bAttack = !Prev.Attacker.IsEmpty() && Next.Attacker.IsEmpty();
		if (bAttack) Attack(Prev.Attacker, Prev.Target);
		// A monster gone from the board breaks where it was last drawn; a battle's victim, when the blow lands.
		for (const FYgoBoardCard& C : Prev.Board)
			if (C.Zone.Contains(TEXT("monster")) && !Next.Board.ContainsByPredicate([&](const FYgoBoardCard& D) { return D.CopyId == C.CopyId; }))
				ShatterAt.Emplace(C.CopyId, Now + (bAttack && C.CopyId == Prev.Target && Figures.Contains(Prev.Attacker) ? .42 * AttackDuration : 0.));
		// The size of a hit is felt before the number is read (the HUD counts it and floats it).
		UYgoFeel* Feel = UYgoFeel::Get(this);
		for (int32 i = 0; Feel && i < 2 && i < Prev.Players.Num() && i < Next.Players.Num(); ++i)
		{
			const int32 Lost = Prev.Players[i].Lp - Next.Players[i].Lp;
			if (Lost > 0) { Feel->AddTrauma(.25f + .6f * FMath::Min(1.f, Lost / 4000.f)); Feel->Play(EYgoSound::Damage); }
			else if (Lost < 0) Feel->Play(EYgoSound::Spell, .8f);
		}
	}
	SeeBacks(Next, Now);
	Prev = Next;
}

void AYgoStage::Attack(const FString& Attacker, const FString& Target)
{
	FFigure* F = Figures.Find(Attacker);
	if (!F) return;  // its figure is not on the table
	FVector To;
	if (const FFigure* T = Target.IsEmpty() ? nullptr : Figures.Find(Target)) To = T->Centre;
	else if (const FPose* P = Target.IsEmpty() ? nullptr : Poses.Find(Target)) To = P->Card;
	// A direct attack flies at the opponent: the near player's across the table (y runs toward them).
	else To = F->Centre + FVector(0, F->bRival ? 1 : -1, 0) * F->Width * 4;
	F->AttackAt = Clock(); F->AttackTo = FVector(To.X, To.Y, 0); F->bImpact = false; F->bDash = false;
}

void AYgoStage::Shatter(const FString& CopyId)
{
	const FPose* P = Poses.Find(CopyId);
	if (P && P->Sprite.IsValid() && Clock() - P->At < 10)
		if (AYgoShatterFx* Fx = GetWorld()->SpawnActor<AYgoShatterFx>())
			Fx->Start(P->Quad, P->Size, P->Width, P->Sprite.Get(), View.Get(), Particles);
	if (FFigure* F = Figures.Find(CopyId)) { DropFigure(*F); Figures.Remove(CopyId); }
	Shattered.Add(CopyId, FPlatformTime::Seconds() + AYgoShatterFx::Duration);
}

void AYgoStage::SeeBacks(const FYgoDuel& Duel, double Now)
{
	UYgoLab* Lab = UYgoLab::Get(this);
	if (!Lab) return;
	for (const FYgoZoneRef& Z : Duel.BacksSeen)
	{
		const FYgoZone* Zone = Lab->GetScene().FindZone(Z.Player, Z.Zone);
		FVector2D Centre; float CardWidth;
		if (!Zone || !FYgoScene::ZonePlace(*Zone, Centre, CardWidth)) continue;
		// Its entrance: a back new in its zone (web/duel.js drawFacedown, the same memory as cards).
		const FString Key = FString::Printf(TEXT("%d|%s"), Z.Player, *Z.Zone);
		const double* Last = BackArrived.Find(Key);
		const bool bNew = (!Last || Now - *Last >= ArrivalMemory) && StartedAt > 0 && Now - StartedAt >= StartupGrace;
		BackArrived.Add(Key, Now);
		FBack* B = Backs.Find(Key);
		if (!B)
		{
			B = &Backs.Add(Key);
			B->Seed = FMath::FRand() * 10.f;
			UMaterialInstanceDynamic* Fx = nullptr;
			B->Glow = NewPlane(TEXT("/Game/YgoAR/M_FxMagic.M_FxMagic"), Fx, 1); B->GlowFx = Fx;
			Param(Fx, TEXT("Mode"), 6.f);
			if (Fx) Fx->SetVectorParameterValue(TEXT("Color"), BackGlow);
			if (Z.Zone.StartsWith(TEXT("monster")) || Z.Zone.StartsWith(TEXT("extra_monster")))
			{
				B->Shadow = NewPlane(TEXT("/Game/YgoAR/M_FxShadow.M_FxShadow"), Fx, 0); B->ShadowFx = Fx;
				B->Solid = NewObject<UProceduralMeshComponent>(this);
				B->Solid->SetCollisionEnabled(ECollisionEnabled::NoCollision);
				B->Solid->CastShadow = false;
				B->Solid->SetupAttachment(GetRootComponent());
				B->Solid->RegisterComponent();
				B->Solid->SetVisibility(false);
				if (UMaterialInterface* M = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/YgoAR/M_FxMetal.M_FxMetal")))
					B->SolidFx = UMaterialInstanceDynamic::Create(M, this);
			}
		}
		B->Centre = FYgoScene::TableToUnreal(Centre); B->Width = CardWidth / 10.f; B->LastSeen = Now;
		if (bNew)
		{
			B->SetAt = Clock();
			if (AYgoFx* Fx = GetWorld()->SpawnActor<AYgoFx>()) Fx->Start(EYgoFx::Set, B->Centre, B->Width, BackGlow, View.Get(), Particles, Hud);
		}
	}
}

UStaticMeshComponent* AYgoStage::NewPlane(const TCHAR* Material, UMaterialInstanceDynamic*& OutFx, int32 SortPriority)
{
	UStaticMeshComponent* C = NewObject<UStaticMeshComponent>(this);
	C->SetStaticMesh(PlaneMesh());
	C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	C->CastShadow = false;
	C->TranslucencySortPriority = SortPriority;
	C->SetupAttachment(GetRootComponent());
	C->RegisterComponent();
	OutFx = nullptr;
	if (UMaterialInterface* M = LoadObject<UMaterialInterface>(nullptr, Material))
	{
		OutFx = UMaterialInstanceDynamic::Create(M, this);
		C->SetMaterial(0, OutFx);
	}
	return C;
}

AYgoStage::FFigure& AYgoStage::FigureFor(const FYgoTrack& Track)
{
	if (FFigure* F = Figures.Find(Track.TrackId)) return *F;
	FFigure& F = Figures.Add(Track.TrackId);
	F.Seed = FMath::FRand() * 10.f;
	UMaterialInstanceDynamic* Fx = nullptr;
	F.Shadow = NewPlane(TEXT("/Game/YgoAR/M_FxShadow.M_FxShadow"), Fx, 0); F.ShadowFx = Fx;
	F.Base = NewPlane(TEXT("/Game/YgoAR/M_FxMagic.M_FxMagic"), Fx, 1); F.BaseFx = Fx;
	F.Sprite = NewPlane(TEXT("/Game/YgoAR/M_FxSprite.M_FxSprite"), Fx, 5); F.SpriteFx = Fx;
	F.Shield = NewPlane(TEXT("/Game/YgoAR/M_FxShield.M_FxShield"), Fx, 6); F.ShieldFx = Fx;
	Param(F.BaseFx, TEXT("Seed"), F.Seed);
	Param(F.ShieldFx, TEXT("Seed"), F.Seed);
	F.Sprite->SetVisibility(false);
	F.Shield->SetVisibility(false);
	// First placement without smoothing.
	FPlace P;
	if (PlaceOf(Track, P))
	{
		F.Target = P;
		F.Centre = FYgoScene::TableToUnreal(P.Centre);
		F.Width = P.Width / 10.f;
	}
	return F;
}

void AYgoStage::DropFigure(FFigure& F)
{
	for (UStaticMeshComponent* C : {F.Sprite.Get(), F.Base.Get(), F.Shadow.Get(), F.Shield.Get(), F.Ghosts[0].Get(), F.Ghosts[1].Get(), F.Ghosts[2].Get()})
		if (C) C->DestroyComponent();
}

void AYgoStage::DropBack(FBack& B)
{
	for (USceneComponent* C : {(USceneComponent*)B.Glow.Get(), (USceneComponent*)B.Shadow.Get(), (USceneComponent*)B.Solid.Get()})
		if (C) C->DestroyComponent();
}

void AYgoStage::Upright(FVector& OutUp, float& OutLean) const
{
	const AYgoTableView* V = View.Get();
	if (!V) { OutUp = FVector::UpVector; OutLean = 0; return; }
	const FVector CamFwd = V->GetCamera()->GetForwardVector(), CamUp = V->GetCamera()->GetUpVector();
	const float Tilt = FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(-CamFwd.Z, -1.f, 1.f)));
	OutLean = FMath::Clamp(1.f - Tilt / 50.f, 0.f, 1.f);
	OutUp = FMath::Lerp(FVector::UpVector, CamUp, OutLean).GetSafeNormal();
}

FVector AYgoStage::TableDown() const
{
	const AYgoTableView* V = View.Get();
	FVector D = V ? -V->GetCamera()->GetUpVector() : FVector(0, 1, 0);
	D.Z = 0;
	return D.IsNearlyZero() ? FVector(0, 1, 0) : D.GetSafeNormal();
}

void AYgoStage::Motes(const FVector& Centre, float Width, const FLinearColor& Color, float PerSecond, float Dt, const FVector& Up)
{
	// Ambient motes rising from a card (web/duel.js drawBase).
	if (!Particles || FMath::FRand() >= Dt * PerSecond) return;
	const float A = FMath::FRand() * 2 * PI, R = Width * .45f * FMath::FRand();
	FYgoParticle M;
	M.Position = Centre + FVector(FMath::Cos(A) * R, FMath::Sin(A) * R, .3f);
	M.Velocity = FVector(0, 0, Width * (.25f + .35f * FMath::FRand())) + Up * Width * .1f;
	M.Color = Color * 2.5f; M.Size = Width * (.02f + .025f * FMath::FRand()); M.Life = 1.4f + .9f * FMath::FRand();
	Particles->Emit(M);
}

void AYgoStage::UpdateFigure(FFigure& F, float Dt, double Now)
{
	UYgoLab* Lab = UYgoLab::Get(this);
	const AYgoTableView* V = View.Get();
	if (!Lab || !V) return;
	using namespace YgoEase;
	const float Smooth = 1.f - FMath::Exp(-15.f * Dt);
	F.Centre = FMath::Lerp(F.Centre, FYgoScene::TableToUnreal(F.Target.Centre), Smooth);
	F.Width = FMath::Lerp(F.Width, F.Target.Width / 10.f, Smooth);
	F.Down = FMath::Lerp(F.Down, FVector(F.Target.Down, 0), Smooth).GetSafeNormal();
	const bool bMonster = F.Kind == TEXT("monster"), bTrap = F.Kind == TEXT("trap");
	const FLinearColor Color = OwnerColor(F.Kind, F.bRival);

	// The duel says how it stands: face-down shows no figure, Defense Position kneels behind a shield.
	FString Position;
	for (const FYgoBoardCard& C : Lab->GetDuel().Board) if (C.CopyId == F.Track.TrackId) { Position = C.Position; break; }
	const bool bFacedown = Position.StartsWith(TEXT("facedown"));
	const bool bDefense = bMonster && Position == TEXT("defense");

	// Contact shadow and the kind's emblem on the card: a ring with two arcs, a slow magic circle, two hexagons.
	F.Shadow->SetWorldLocation(F.Centre + FVector(0, 0, .02f));
	F.Shadow->SetWorldScale3D(FVector(F.Width * 1.3f / 100.f));
	Param(F.ShadowFx, TEXT("Alpha"), bFacedown ? 0.f : .45f);
	const float U = OnPlane * F.Width;
	const float BaseRadius = bMonster ? F.Width * .575f : bTrap ? 1.15f * U : 1.05f * U / .95f;
	Lay(F.Base, F.Centre, BaseRadius, .04f);
	if (F.BaseFx)
	{
		F.BaseFx->SetVectorParameterValue(TEXT("Color"), Color);
		Param(F.BaseFx, TEXT("Mode"), bMonster ? 1.f : bTrap ? 4.f : 0.f);
		Param(F.BaseFx, TEXT("Span"), 1.15f);
		Param(F.BaseFx, TEXT("Progress"), 1.f);
		const bool bChosen = Hud.IsValid() && Hud->Attacker() == F.Track.TrackId;  // about to attack: its ring burns
		const float Alpha = bChosen ? 1.5f : bMonster ? .7f + .2f * FMath::Sin(Now / .6 + F.Seed) : bTrap ? .45f + .4f * FMath::Abs(FMath::Sin(Now / .3 + F.Seed)) : .5f;
		if (bChosen) F.BaseFx->SetVectorParameterValue(TEXT("Color"), Fire);
		Param(F.BaseFx, TEXT("Alpha"), bFacedown ? 0.f : Alpha);
	}

	UTexture2D* Tex = Lab->Sprite(F.Track);
	auto Hide = [&F]
	{
		F.Sprite->SetVisibility(false); F.Shield->SetVisibility(false);
		for (UStaticMeshComponent* G : F.Ghosts) if (G) G->SetVisibility(false);
	};
	if (!Tex || bFacedown) { Hide(); return; }

	const FVector CamRight = V->GetCamera()->GetRightVector();
	float Height = F.Width * (bMonster ? (bDefense ? .95f : 1.25f) : 1.05f);
	float Scale = 1.f, Alpha = bMonster ? (bDefense ? .85f : 1.f) : .95f, Flash = 0.f, Rot = 0.f, Lift = 0.f, Squash = 1.f, Bob = 0.f, Breathe = 1.f;
	FVector Slide = FVector::ZeroVector, Dash = FVector::ZeroVector;
	float DashK = 0.f, DashT = -1.f;
	if (bMonster)
	{
		Rot = FMath::Sin(Now / .95 + F.Seed) * .03f;
		Bob = FMath::Sin(Now / .65 + F.Seed) * .035f * Height;
		Breathe = 1 + FMath::Sin(Now / .52 + F.Seed) * .015f;
		// Summon: appears at 30 % of the sequence with an overshoot and a white flash (as the 2D view).
		const float Since = Now - F.SummonAt;
		if (Since < AYgoSummonFx::Duration)
		{
			const float T = Since / AYgoSummonFx::Duration, W = Span(T, .3f, .62f);
			if (W <= 0) { Hide(); return; }
			Scale = .5f + .5f * Back(W); Alpha *= FMath::Min(1.f, W * 2); Flash = FMath::Square(1 - Span(T, .3f, .6f));
		}
		// Attack: wind-up, dash (with after-images), hold, return; the blow lands at 42 %.
		const float Attacking = Now - F.AttackAt;
		if (Attacking < AttackDuration)
		{
			const float T = DashT = Attacking / AttackDuration;
			if (!F.bDash && T >= .2f)
			{
				F.bDash = true;
				if (UYgoFeel* Feel = UYgoFeel::Get(this)) Feel->Play(EYgoSound::Dash);
			}
			Dash = F.AttackTo - FVector(F.Centre.X, F.Centre.Y, 0);
			DashK = T < .2f ? -.12f * Out(T / .2f) : T < .42f ? -.12f + .92f * In(Span(T, .2f, .42f)) : T < .58f ? .8f : .8f * (1 - Out(Span(T, .58f, 1)));
			Slide = Dash * DashK;
			const float Side = FVector::DotProduct(Dash, CamRight) < 0 ? -1.f : 1.f;
			Rot += (T < .2f ? -.12f : T < .46f ? .1f : 0.f) * Side;
			Squash = T < .2f ? .94f : T < .46f ? 1.06f : 1.f;
			if (!F.bImpact && T >= .42f)
			{
				F.bImpact = true;
				if (AYgoFx* Fx = GetWorld()->SpawnActor<AYgoFx>())
					Fx->Start(EYgoFx::Impact, F.AttackTo, F.Width, F.bRival ? OwnerColor(TEXT("monster"), true) : Fire, View.Get(), Particles, Hud);
			}
		}
	}
	else
	{
		// A spell hovers calmly; a trap is restless, waiting. Their activation pops them in.
		if (bTrap) { Rot = FMath::Sin(Now / .17 + F.Seed) * .018f; Slide = CamRight * FMath::Sin(Now / .09 + F.Seed) * .004f * Height; }
		else Lift = FMath::Sin(Now / .9 + F.Seed) * .05f * Height;
		const float T = (Now - F.ActivateAt) / AYgoFx::Duration(bTrap ? EYgoFx::Trap : EYgoFx::Spell);
		if (T < 1)
		{
			if (bTrap)
			{
				const float W = Span(T, 0, .35f);
				Scale = .3f + .7f * Back(W); Alpha *= W; Rot += FMath::Sin(T * 60) * .08f * (1 - T); Flash = 1 - Span(T, .15f, .6f);
			}
			else
			{
				const float W = Span(T, .15f, .55f);
				Scale = .4f + .6f * Back(W); Alpha *= W; Lift += Height * .25f * (1 - Out(Span(T, .15f, .9f))); Flash = 1 - Span(T, .3f, .8f);
			}
			if (Alpha <= 0) { Hide(); return; }
		}
	}

	FVector Up; float Lean;
	Upright(Up, Lean);
	const float Width = Height * Tex->GetSizeX() / FMath::Max(1, Tex->GetSizeY());
	const FVector2D Size(Width * Scale, Height * Scale * Breathe * Squash);
	// Where the figure stands, for its card's centre moved by Slide: its feet toward the image's
	// bottom, so it covers its card as the 2D view's figure does.
	auto Place = [&](const FVector& Move, float Rotate, const FVector2D& S, UStaticMeshComponent* Quad) -> FTransform
	{
		const FVector Feet = F.Centre + Move + F.Down * (.38f * Height * Lean) + Up * Lift + FVector(0, 0, .3f);
		const FVector ToCamera = (V->CameraLocation() - Feet).GetSafeNormal();
		const FVector Upward = Up.RotateAngleAxisRad(Rotate, ToCamera);
		const FTransform Pose(FRotationMatrix::MakeFromYZ(-Upward, ToCamera).ToQuat(), Feet + Upward * (S.Y / 2 + Bob));
		Quad->SetWorldLocationAndRotation(Pose.GetLocation(), Pose.GetRotation());
		Quad->SetWorldScale3D(FVector(S.X, S.Y, 100) * (SpritePad / 100.f));
		return Pose;
	};
	const FTransform Pose = Place(Slide, Rot, Size, F.Sprite);
	F.Sprite->SetVisibility(true);
	if (F.SpriteFx)
	{
		F.SpriteFx->SetTextureParameterValue(TEXT("Sprite"), Tex);
		Param(F.SpriteFx, TEXT("Alpha"), Alpha);
		Param(F.SpriteFx, TEXT("Flash"), Flash);
		F.SpriteFx->SetVectorParameterValue(TEXT("Glow"), Color);
	}
	if (bMonster) Poses.Add(F.Track.TrackId, {Pose, Size, F.Centre, F.Width, Tex, Now});

	// After-images trailing the dash.
	for (int32 i = 0; i < 3; ++i)
	{
		const bool bOn = DashT > .2f && DashT < .46f;
		if (bOn && !F.Ghosts[i])
		{
			UMaterialInstanceDynamic* Fx = nullptr;
			F.Ghosts[i] = NewPlane(TEXT("/Game/YgoAR/M_FxSprite.M_FxSprite"), Fx, 4); F.GhostFx[i] = Fx;
		}
		if (!F.Ghosts[i]) continue;
		F.Ghosts[i]->SetVisibility(bOn);
		if (!bOn) continue;
		const int32 Back3 = 3 - i;  // the furthest behind is the faintest
		Place(Dash * FMath::Max(-.12f, DashK - Back3 * .12f), Rot, Size, F.Ghosts[i]);
		if (UMaterialInstanceDynamic* G = F.GhostFx[i])
		{
			G->SetTextureParameterValue(TEXT("Sprite"), Tex);
			Param(G, TEXT("Alpha"), .18f * (4 - Back3) / 3.f);
			G->SetVectorParameterValue(TEXT("Glow"), Color);
		}
	}

	// Defense Position: the hex shield in front of the kneeling monster.
	F.Shield->SetVisibility(bDefense);
	if (bDefense)
	{
		const FVector Front = (V->CameraLocation() - Pose.GetLocation()).GetSafeNormal();
		// Low on the figure (its Y axis runs down the image), a little toward the camera.
		const FVector At = Pose.GetLocation() + Pose.GetRotation().GetAxisY() * (Size.Y * .5f - F.Width * .32f) + Front * .5f;
		F.Shield->SetWorldLocationAndRotation(At, Pose.GetRotation());
		F.Shield->SetWorldScale3D(FVector(F.Width * .3f / .95f * 2 / 100.f));
		Param(F.ShieldFx, TEXT("Alpha"), Alpha);
	}
	Motes(F.Centre, F.Width, Color, 3.f, Dt, Up);
}

void AYgoStage::UpdateBack(FBack& B, float Dt, double Now)
{
	UYgoLab* Lab = UYgoLab::Get(this);
	const AYgoTableView* V = View.Get();
	if (!Lab || !V) return;
	using namespace YgoEase;
	// The set's entrance brings it in (2D: from 35 % to 90 % of it).
	const float A = Span((Now - B.SetAt) / AYgoFx::Duration(EYgoFx::Set), .35f, .9f);
	const float Pulse = .5f + .5f * FMath::Sin(Now / .7 + B.Seed);
	const float ZoneWidth = B.Width / .72f;
	Lay(B.Glow, B.Centre, .6f * ZoneWidth, .03f);
	Param(B.GlowFx, TEXT("Alpha"), (.18f + .08f * Pulse) * A);
	if (!B.Solid) return;  // a Spell & Trap Zone: only the warm light
	FVector Up; float Lean;
	Upright(Up, Lean);
	Motes(B.Centre, B.Width, BackGlow, 2.4f * A, Dt, Up);

	// The Millennium shield of a face-down Defense Position monster: never its identity. A solid of
	// gold and lacquer, built once its drawings and their relief have arrived from the lab.
	UTexture2D* Front = Lab->Image(ShieldFront);
	UTexture2D* Rear = Lab->Image(ShieldBack);
	UTexture2D* FrontRelief = Lab->DataImage(ShieldFrontRelief);
	UTexture2D* RearRelief = Lab->DataImage(ShieldBackRelief);
	const FYgoPixels* FrontPixels = Lab->Pixels(ShieldFrontRelief);
	const FYgoPixels* RearPixels = Lab->Pixels(ShieldBackRelief);
	if (!B.bSolidBuilt && Front && Rear && FrontRelief && RearRelief && FrontPixels && RearPixels && B.SolidFx)
	{
		const FShieldMesh& Mesh = ShieldMesh(*FrontPixels, *RearPixels);
		B.Solid->CreateMeshSection_LinearColor(0, Mesh.Vertices, Mesh.Triangles, TArray<FVector>(), Mesh.UVs, Mesh.Colors, TArray<FProcMeshTangent>(), false);
		B.Solid->SetMaterial(0, B.SolidFx);
		B.SolidFx->SetTextureParameterValue(TEXT("ArtFront"), Front);
		B.SolidFx->SetTextureParameterValue(TEXT("ArtBack"), Rear);
		B.SolidFx->SetTextureParameterValue(TEXT("ReliefFront"), FrontRelief);
		B.SolidFx->SetTextureParameterValue(TEXT("ReliefBack"), RearRelief);
		B.bSolidBuilt = true;
	}
	// It comes in as the set's spiral closes: it drops into place growing, spinning fast, and the spin
	// runs down to one turn every 6 s. A solid cannot fade in, so it appears small in a flash of gold.
	const float Since = float(Now - B.SetAt) - .35f * AYgoFx::Duration(EYgoFx::Set);
	const bool bShown = B.bSolidBuilt && Since > 0;
	// Until then it is drawn as a speck under its card: its shaders load on first use, and a solid
	// whose shaders are not there yet comes out black.
	B.Solid->SetVisibility(B.bSolidBuilt);
	B.Shadow->SetVisibility(bShown);
	if (!bShown)
	{
		B.Solid->SetWorldLocation(B.Centre - FVector(0, 0, .5f));
		B.Solid->SetWorldScale3D(FVector(1e-4f));
		return;
	}
	const float Pop = Clamp01(Since / .55f), Size = FMath::Max(.02f, Back(Pop));
	const float Height = .95f * ZoneWidth * Size;
	const float Width = Height * Front->GetSizeX() / FMath::Max(1, Front->GetSizeY());
	const float Bob = FMath::Sin(Now / .9 + B.Seed) * .025f * ZoneWidth;
	const float Drop = (1 - Out(Pop)) * .45f * ZoneWidth;
	// Seen from above it turns lying over the table: high enough that its edge never dips into it
	// (the glow and the shadow on the table would be drawn over the part below).
	const FVector Feet = B.Centre + TableDown() * (.38f * Height * Lean) + FVector(0, 0, .3f + .56f * Width * Lean);
	const FVector Centre = Feet + Up * (Height / 2 + Bob + Drop);
	const FVector ToCamera = (V->CameraLocation() - Centre).GetSafeNormal();
	const float SpinUp = FMath::Pow(1 - Clamp01(Since / 2.4f), 3.f) * 2.5f;  // turns still to shed
	const float Angle = (FMath::Fmod(Now / 6.0 + B.Seed, 1.0) - SpinUp) * 2 * PI;
	// It does not turn like a sign on a pole: its axis nods a little, slowly.
	const FQuat Facing = FRotationMatrix::MakeFromYZ(-Up, ToCamera).ToQuat();
	const float Nod = .11f * FMath::Sin(Now / 1.9 + B.Seed * 1.7f);
	const FQuat Turn = FQuat(Up, Angle) * FQuat(Facing.GetAxisX(), Nod) * Facing;
	const float C = FVector::DotProduct(Turn.GetAxisZ(), ToCamera);  // 1 facing the camera, 0 edge-on
	B.Solid->SetWorldLocationAndRotation(Centre, Turn);
	B.Solid->SetWorldScale3D(FVector(Width / 100.f, Height / 100.f, Height / 100.f));
	if (UMaterialInstanceDynamic* M = B.SolidFx)
	{
		auto Axis = [](const FVector& A) { return FLinearColor(A.X, A.Y, A.Z, 0); };
		M->SetVectorParameterValue(TEXT("AxisX"), Axis(Turn.GetAxisX()));
		M->SetVectorParameterValue(TEXT("AxisY"), Axis(Turn.GetAxisY()));
		M->SetVectorParameterValue(TEXT("AxisZ"), Axis(Turn.GetAxisZ()));
		// The key light: over the camera's left shoulder, where the drawings' own light comes from.
		const UCameraComponent* Cam = V->GetCamera();
		M->SetVectorParameterValue(TEXT("Light"), Axis((ToCamera * .75f + Cam->GetUpVector() * .5f - Cam->GetRightVector() * .42f).GetSafeNormal()));
		Param(M, TEXT("Flash"), .9f * FMath::Square(1 - Clamp01(Since / .6f)));
	}
	// Its shadow on the card: narrower as it turns edge-on, fainter while it is still in the air.
	Lay(B.Shadow, B.Centre, .5f * ZoneWidth * Size * (.7f + .3f * FMath::Abs(C)), .02f);
	Param(B.ShadowFx, TEXT("Alpha"), .5f * Out(Pop));
}

void AYgoStage::Tick(float Dt)
{
	Super::Tick(Dt);
	const double Wall = FPlatformTime::Seconds();
	if (StartedAt <= 0) StartedAt = Wall;  // the first frame on screen, after loading (can take half a minute)
	if (ReplayAt > 0 && Wall - StartedAt >= ReplayAt) { Arrived.Empty(); BackArrived.Empty(); ReplayAt = 0; }
	if (DemoAt > 0 && Wall - StartedAt >= DemoAt) Demo(Wall - StartedAt - DemoAt);
	for (int32 i = ShatterAt.Num() - 1; i >= 0; --i)
		if (Wall >= ShatterAt[i].Value) { Shatter(ShatterAt[i].Key); ShatterAt.RemoveAt(i); }
	// What the camera sees runs on the wall clock; figures and effects can stand still for a blow.
	UYgoFeel* Feel = UYgoFeel::Get(this);
	const double Now = Clock();
	const float FxDt = Feel && Feel->IsFrozen() ? 0.f : Dt;
	for (auto It = Figures.CreateIterator(); It; ++It)
	{
		if (Wall - It->Value.LastSeen > FigureHold) { DropFigure(It->Value); It.RemoveCurrent(); continue; }
		UpdateFigure(It->Value, FxDt, Now);
	}
	for (auto It = Backs.CreateIterator(); It; ++It)
	{
		if (Wall - It->Value.LastSeen > BackHold) { DropBack(It->Value); It.RemoveCurrent(); continue; }
		UpdateBack(It->Value, FxDt, Now);
	}
	for (auto It = Poses.CreateIterator(); It; ++It) if (Now - It->Value.At > 10) It.RemoveCurrent();
	UpdateAskMark(Wall);
	UpdateZoneMarks();
	PickWithMouse();
	if (const AYgoTableView* V = View.Get())
	{
		Particles->Step(FxDt, V->CameraLocation());
		if (Warm) Warm->SetWorldLocation(V->CameraLocation() + V->GetCamera()->GetForwardVector() * 20.f);
	}
	Capture(Wall);
}

void AYgoStage::UpdateAskMark(double Now)
{
	const UYgoLab* Lab = UYgoLab::Get(this);
	const FYgoQuestion* Q = Hud.IsValid() ? Hud->AskedQuestion() : nullptr;
	const FYgoZone* Zone = Q && Lab ? Lab->GetScene().FindZone(Q->Player, Q->Zone) : nullptr;
	if (Zone && Zone->Polygon.Num() != 4) Zone = nullptr;
	if (Zone && !AskMark)
	{
		UMaterialInstanceDynamic* Fx = nullptr;
		AskMark = NewPlane(TEXT("/Game/YgoAR/M_FxMagic.M_FxMagic"), Fx, 3); AskMarkFx = Fx;
		Param(Fx, TEXT("Mode"), 7.f);
		if (Fx) Fx->SetVectorParameterValue(TEXT("Color"), FLinearColor::FromSRGBColor(FColor(255, 214, 130)));
	}
	if (AskMark) AskMark->SetVisibility(Zone != nullptr);
	if (!Zone) return;
	const TArray<FVector2D>& P = Zone->Polygon;  // TL, TR, BR, BL
	const FVector2D Across = P[1] - P[0];
	const float Width = Across.Size() / 10.f, Height = (P[3] - P[0]).Size() / 10.f;
	AskMark->SetWorldLocationAndRotation(FYgoScene::TableToUnreal((P[0] + P[1] + P[2] + P[3]) / 4, .06f),
		FRotator(0, FMath::RadiansToDegrees(FMath::Atan2(Across.Y, Across.X)), 0));
	AskMark->SetWorldScale3D(FVector(Width / 100.f, Height / 100.f, 1));
	Param(AskMarkFx, TEXT("Span"), Width / FMath::Max(Height, .1f));
	Param(AskMarkFx, TEXT("Alpha"), .75f + .25f * FMath::Sin(Now * 3.5));
}

void AYgoStage::UpdateZoneMarks()
{
	const UYgoLab* Lab = UYgoLab::Get(this);
	const bool bShow = Lab && Hud.IsValid() && Hud->ShowsZones();
	if (!bShow) { for (UStaticMeshComponent* C : ZoneMarks) C->SetVisibility(false); return; }
	const TArray<FYgoZone>& Zones = Lab->GetScene().Zones;
	while (ZoneMarks.Num() < Zones.Num())
	{
		UMaterialInstanceDynamic* Fx = nullptr;
		ZoneMarks.Add(NewPlane(TEXT("/Game/YgoAR/M_FxMagic.M_FxMagic"), Fx, 1)); ZoneMarkFx.Add(Fx);
		Param(Fx, TEXT("Mode"), 7.f);
		Param(Fx, TEXT("Alpha"), .55f);
	}
	for (int32 i = 0; i < ZoneMarks.Num(); ++i)
	{
		const bool bZone = Zones.IsValidIndex(i) && Zones[i].Polygon.Num() == 4;
		ZoneMarks[i]->SetVisibility(bZone);
		if (!bZone) continue;
		const TArray<FVector2D>& P = Zones[i].Polygon;
		const FVector2D Across = P[1] - P[0];
		const float Width = Across.Size() / 10.f, Height = (P[3] - P[0]).Size() / 10.f;
		ZoneMarks[i]->SetWorldLocationAndRotation(FYgoScene::TableToUnreal((P[0] + P[1] + P[2] + P[3]) / 4, .05f),
			FRotator(0, FMath::RadiansToDegrees(FMath::Atan2(Across.Y, Across.X)), 0));
		ZoneMarks[i]->SetWorldScale3D(FVector(Width / 100.f, Height / 100.f, 1));
		Param(ZoneMarkFx[i], TEXT("Span"), Width / FMath::Max(Height, .1f));
		if (ZoneMarkFx[i]) ZoneMarkFx[i]->SetVectorParameterValue(TEXT("Color"), OwnerColor(Zones[i].Zone.StartsWith(TEXT("spell")) ? TEXT("spell") : TEXT("monster"), Zones[i].Player == 1));
	}
}

void AYgoStage::PickWithMouse()
{
	APlayerController* PC = GetWorld()->GetFirstPlayerController();
	if (!PC || !Hud.IsValid() || !PC->WasInputKeyJustPressed(EKeys::LeftMouseButton)) return;
	FVector Origin, Direction;
	if (!PC->DeprojectMousePositionToWorld(Origin, Direction) || Direction.Z > -1e-3) return;
	const FVector Point = Origin + Direction * (-Origin.Z / Direction.Z);
	// The figure stands over its card, so a click on either counts: the nearest within a card and a half.
	FString Best;
	double BestDistance = TNumericLimits<double>::Max();
	for (const TPair<FString, FFigure>& It : Figures)
	{
		const double Distance = FVector2D::Distance(FVector2D(Point), FVector2D(It.Value.Centre));
		if (It.Value.Kind == TEXT("monster") && Distance < It.Value.Width * 1.5f && Distance < BestDistance) { BestDistance = Distance; Best = It.Key; }
	}
	if (!Best.IsEmpty()) Hud->PickCard(Best);
}

void AYgoStage::Demo(double Since)
{
	static const double Beats[] = {0, 3, 5.5, 8, 11, 13};
	if (DemoStep >= UE_ARRAY_COUNT(Beats) || Since < Beats[DemoStep]) return;
	UYgoLab* Lab = UYgoLab::Get(this);
	TArray<FString> Monsters;  // left to right on the screen
	for (const TPair<FString, FFigure>& It : Figures) if (It.Value.Kind == TEXT("monster")) Monsters.Add(It.Key);
	if (const AYgoTableView* V = View.Get())
	{
		const FVector Right = V->GetCamera()->GetRightVector();
		Monsters.Sort([&](const FString& A, const FString& B) { return FVector::DotProduct(Figures[A].Centre, Right) < FVector::DotProduct(Figures[B].Centre, Right); });
	}
	auto ZoneFx = [&](EYgoFx Kind, const TCHAR* Zone, const FText& Title)
	{
		const FYgoZone* Z = Lab ? Lab->GetScene().FindZone(0, Zone) : nullptr;
		FVector2D Centre; float Width;
		if (!Z || !FYgoScene::ZonePlace(*Z, Centre, Width)) return;
		const FLinearColor Color = OwnerColor(Kind == EYgoFx::Trap ? TEXT("trap") : TEXT("spell"), false);
		if (AYgoFx* Fx = GetWorld()->SpawnActor<AYgoFx>()) Fx->Start(Kind, FYgoScene::TableToUnreal(Centre), Width / 10.f, Color, View.Get(), Particles, Hud);
		if (Hud.IsValid()) Hud->ShowBanner(Title, Kind == EYgoFx::Trap ? LOCTEXT("Trap", "TRAMPA") : LOCTEXT("Spell", "MAGIA"), Color);
	};
	const double Now = FPlatformTime::Seconds();
	switch (DemoStep++)
	{
	case 0: Arrived.Empty(); BackArrived.Empty(); break;  // every card on the table makes its entrance
	case 1: ZoneFx(EYgoFx::Spell, TEXT("spell:1"), LOCTEXT("DemoSpell", "Demostración: Magia")); break;
	case 2: ZoneFx(EYgoFx::Trap, TEXT("spell:3"), LOCTEXT("DemoTrap", "Demostración: Trampa")); break;
	case 3:
		if (Monsters.Num() >= 2)
		{
			Attack(Monsters[0], Monsters[1]);
			ShatterAt.Emplace(Monsters[1], Now + .42 * AttackDuration);
			if (Hud.IsValid()) Hud->PreviewLp(1, -1200);
		}
		break;
	case 4:
		if (Monsters.Num() >= 1)
		{
			Attack(Monsters.Last(), FString());
			if (Hud.IsValid()) Hud->PreviewLp(1, -2500);
			if (UYgoFeel* Feel = UYgoFeel::Get(this)) Feel->AddTrauma(.6f);
		}
		break;
	default: DemoAt = 0; break;
	}
}

void AYgoStage::Capture(double Now)
{
	const double Age = Now - StartedAt;
	if (QuitAfter > 0 && Age > QuitAfter) FPlatformMisc::RequestExit(false);
	if (!ShotDir.IsEmpty() && Age >= NextShotAt)
	{
		NextShotAt = Age + ShotEvery;
		FScreenshotRequest::RequestScreenshot(FPaths::Combine(ShotDir, FString::Printf(TEXT("shot_%04d.png"), ShotCount++)), true, false);
	}
}

#undef LOCTEXT_NAMESPACE
