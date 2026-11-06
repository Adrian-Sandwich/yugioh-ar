#include "YgoLab.h"

#include "Async/Async.h"
#include "Dom/JsonObject.h"
#include "Engine/GameInstance.h"
#include "Engine/Texture2D.h"
#include "Engine/World.h"
#include "GenericPlatform/GenericPlatformHttp.h"
#include "HttpModule.h"
#include "IImageWrapper.h"
#include "IImageWrapperModule.h"
#include "Interfaces/IHttpResponse.h"
#include "Misc/CommandLine.h"
#include "Modules/ModuleManager.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

DEFINE_LOG_CATEGORY_STATIC(LogYgoLab, Log, All);

namespace
{
	IImageWrapperModule* ImageWrappers = nullptr;

	// A field as text whether the lab sent a string or a number (ids are either); empty for null or absent.
	FString Str(const TSharedPtr<FJsonObject>& O, const TCHAR* Field)
	{
		const TSharedPtr<FJsonValue> V = O->TryGetField(Field);
		FString S;
		return V.IsValid() && !V->IsNull() && V->TryGetString(S) ? S : FString();
	}

	int32 Int(const TSharedPtr<FJsonObject>& O, const TCHAR* Field, int32 Default = 0)
	{
		double D;
		return O->TryGetNumberField(Field, D) ? FMath::RoundToInt32(D) : Default;
	}

	TArray<TSharedPtr<FJsonValue>> Arr(const TSharedPtr<FJsonObject>& O, const TCHAR* Field)
	{
		const TArray<TSharedPtr<FJsonValue>>* A;
		return O->TryGetArrayField(Field, A) ? *A : TArray<TSharedPtr<FJsonValue>>();
	}

	FVector2D Point(const TSharedPtr<FJsonValue>& V)
	{
		const TArray<TSharedPtr<FJsonValue>>& P = V->AsArray();
		return P.Num() >= 2 ? FVector2D(P[0]->AsNumber(), P[1]->AsNumber()) : FVector2D::ZeroVector;
	}

	TSharedPtr<FJsonValue> Raw(const TSharedPtr<FJsonObject>& O, const TCHAR* Field)
	{
		const TSharedPtr<FJsonValue> V = O->TryGetField(Field);
		return V.IsValid() && !V->IsNull() ? V : nullptr;
	}

	TArray<FYgoOption> Options(const TSharedPtr<FJsonObject>& O, const TCHAR* Field)
	{
		TArray<FYgoOption> Out;
		for (const TSharedPtr<FJsonValue>& V : Arr(O, Field))
		{
			const TSharedPtr<FJsonObject> Item = V->AsObject();
			if (Item.IsValid()) Out.Add({Str(Item, TEXT("type")), Str(Item, TEXT("label"))});
		}
		return Out;
	}

	bool DecodeImage(EImageFormat Format, const TArray<uint8>& Bytes, TArray<uint8>& OutBgra, int32& OutW, int32& OutH)
	{
		TSharedPtr<IImageWrapper> W = ImageWrappers ? ImageWrappers->CreateImageWrapper(Format) : nullptr;
		if (!W.IsValid() || !W->SetCompressed(Bytes.GetData(), Bytes.Num()) || !W->GetRaw(ERGBFormat::BGRA, 8, OutBgra)) return false;
		OutW = W->GetWidth();
		OutH = W->GetHeight();
		return OutW > 0 && OutH > 0;
	}
}

UYgoLab* UYgoLab::Get(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	UGameInstance* GI = World ? World->GetGameInstance() : nullptr;
	return GI ? GI->GetSubsystem<UYgoLab>() : nullptr;
}

void UYgoLab::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	ImageWrappers = &FModuleManager::LoadModuleChecked<IImageWrapperModule>(TEXT("ImageWrapper"));
	BaseUrl = GetDefault<UYgoSettings>()->LabUrl;
	FParse::Value(FCommandLine::Get(), TEXT("LabUrl="), BaseUrl);
	BaseUrl.RemoveFromEnd(TEXT("/"));
	StartedAt = FPlatformTime::Seconds();
	UE_LOG(LogYgoLab, Display, TEXT("Lab: %s"), *BaseUrl);
}

void UYgoLab::Deinitialize()
{
	OnFrame.Clear(); OnScene.Clear(); OnDuel.Clear();
	Super::Deinitialize();
}

void UYgoLab::Tick(float DeltaTime)
{
	const double Now = FPlatformTime::Seconds();
	if (!bSnapshotInFlight && !bDecoding) RequestSnapshot();
	if (!bAnalysisInFlight && Now >= NextAnalysisAt)
	{
		// The lab's recognition loop sleeps unless a client long-polls it (pipeline.AnalysisLoop), and
		// tracks, duel and arrivals all come from it. view=table: every card on the table gets its
		// figure, also between the zones, and no analysed JPEG comes back.
		bAnalysisInFlight = true;
		RequestJson(FString::Printf(TEXT("/analysis?after=%lld&view=table"), AnalysisSequence), [this](TSharedPtr<FJsonObject> Json, const FString&)
		{
			bAnalysisInFlight = false;
			double Sequence;
			if (Json.IsValid() && Json->TryGetNumberField(TEXT("sequence"), Sequence)) AnalysisSequence = (int64)Sequence;
			else NextAnalysisAt = FPlatformTime::Seconds() + .25;  // nothing new yet, or the lab is down: not every tick
		});
	}
	if (!bDuelInFlight && Now >= NextDuelAt)
	{
		bDuelInFlight = true; NextDuelAt = Now + 0.5;
		RequestJson(TEXT("/duel"), [this](TSharedPtr<FJsonObject> Json, const FString&) { bDuelInFlight = false; ParseDuel(Json); });
	}
	if (!bSceneInFlight && Now >= NextSceneAt)
	{
		bSceneInFlight = true; NextSceneAt = Now + 2.0;
		RequestJson(TEXT("/scene"), [this](TSharedPtr<FJsonObject> Json, const FString& Raw)
		{
			bSceneInFlight = false;
			if (!Json.IsValid()) { if (Scene.bValid) { Scene.bValid = false; LastSceneKey.Empty(); OnScene.Broadcast(); } return; }
			if (Raw == LastSceneKey) return;
			LastSceneKey = Raw;
			ParseScene(Json);
			OnScene.Broadcast();
		});
	}
}

void UYgoLab::RequestSnapshot()
{
	bSnapshotInFlight = true;
	TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Req = FHttpModule::Get().CreateRequest();
	Req->SetURL(FString::Printf(TEXT("%s/snapshot?t=%lld"), *BaseUrl, (long long)(FPlatformTime::Seconds() * 1000)));
	Req->SetVerb(TEXT("GET"));
	Req->SetTimeout(5.0f);
	TWeakObjectPtr<UYgoLab> Weak(this);
	Req->OnProcessRequestComplete().BindLambda([Weak](FHttpRequestPtr, FHttpResponsePtr Response, bool bOk)
	{
		UYgoLab* Self = Weak.Get();
		if (!Self) return;
		Self->bSnapshotInFlight = false;
		if (!bOk || !Response.IsValid() || Response->GetResponseCode() != 200) return;
		Self->ParseTracks(Response->GetHeader(TEXT("X-Tracks")));
		Self->bDecoding = true;
		Async(EAsyncExecution::ThreadPool, [Weak, Jpeg = Response->GetContent()]()
		{
			TArray<uint8> Bgra; int32 W = 0, H = 0;
			const bool bDecoded = DecodeImage(EImageFormat::JPEG, Jpeg, Bgra, W, H);
			AsyncTask(ENamedThreads::GameThread, [Weak, Bgra = MoveTemp(Bgra), W, H, bDecoded]() mutable
			{
				UYgoLab* Self = Weak.Get();
				if (!Self) return;
				Self->bDecoding = false;
				if (bDecoded) Self->UploadFrame(MoveTemp(Bgra), W, H);
			});
		});
	});
	Req->ProcessRequest();
}

void UYgoLab::RequestJson(const FString& Path, TFunction<void(TSharedPtr<FJsonObject>, const FString&)> Done)
{
	TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Req = FHttpModule::Get().CreateRequest();
	Req->SetURL(BaseUrl + Path);
	Req->SetVerb(TEXT("GET"));
	Req->SetTimeout(5.0f);
	TWeakObjectPtr<UYgoLab> Weak(this);
	Req->OnProcessRequestComplete().BindLambda([Weak, Done = MoveTemp(Done)](FHttpRequestPtr, FHttpResponsePtr Response, bool bOk)
	{
		if (!Weak.IsValid()) return;
		TSharedPtr<FJsonObject> Json;
		FString Raw;
		if (bOk && Response.IsValid() && Response->GetResponseCode() == 200)
		{
			Raw = Response->GetContentAsString();
			FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Raw), Json);
		}
		Done(Json, Raw);
	});
	Req->ProcessRequest();
}

void UYgoLab::ParseTracks(const FString& Header)
{
	PendingTracks.Reset();
	TArray<TSharedPtr<FJsonValue>> Items;
	if (Header.IsEmpty() || !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Header), Items)) return;
	for (const TSharedPtr<FJsonValue>& V : Items)
	{
		const TSharedPtr<FJsonObject> O = V->AsObject();
		if (!O.IsValid()) continue;
		const TArray<TSharedPtr<FJsonValue>> Corners = Arr(O, TEXT("corners"));
		if (Corners.Num() != 4) continue;
		FYgoTrack T;
		T.TrackId = Str(O, TEXT("track_id"));
		T.CardId = Str(O, TEXT("card_id"));
		T.Name = Str(O, TEXT("name"));
		T.SpriteRef = Str(O, TEXT("sprite_ref"));
		T.SpriteUrl = Str(O, TEXT("sprite_url"));
		bool bStable = false;
		T.bStable = O->TryGetBoolField(TEXT("stable"), bStable) && bStable;
		for (int32 i = 0; i < 4; ++i) T.Corners[i] = Point(Corners[i]);
		PendingTracks.Add(MoveTemp(T));
	}
}

void UYgoLab::UploadFrame(TArray<uint8>&& Bgra, int32 Width, int32 Height)
{
	if (!Video || Video->GetSizeX() != Width || Video->GetSizeY() != Height)
	{
		Video = UTexture2D::CreateTransient(Width, Height, PF_B8G8R8A8, TEXT("YgoVideo"));
		Video->SRGB = true;
		Video->Filter = TF_Bilinear;
		Video->NeverStream = true;
		Video->UpdateResource();
	}
	// The render thread copies the pixels later: the buffer and the region live until it is done.
	FUpdateTextureRegion2D* Region = new FUpdateTextureRegion2D(0, 0, 0, 0, Width, Height);
	TArray<uint8>* Data = new TArray<uint8>(MoveTemp(Bgra));
	Video->UpdateTextureRegions(0, 1, Region, Width * 4, 4, Data->GetData(),
		[Data](uint8*, const FUpdateTextureRegion2D* R) { delete Data; delete R; });
	Tracks = MoveTemp(PendingTracks);
	LastFrameAt = FPlatformTime::Seconds();
	OnFrame.Broadcast();
}

void UYgoLab::ParseScene(const TSharedPtr<FJsonObject>& Json)
{
	FYgoScene S;
	const TArray<TSharedPtr<FJsonValue>> Size = Arr(Json, TEXT("image_size"));
	if (Size.Num() == 2) S.ImageSize = FIntPoint(Size[0]->AsNumber(), Size[1]->AsNumber());
	const TSharedPtr<FJsonObject>* K;
	const TSharedPtr<FJsonObject>* Cam;
	if (!Json->TryGetObjectField(TEXT("intrinsics"), K) || !Json->TryGetObjectField(TEXT("camera"), Cam)) return;
	S.Fx = (*K)->GetNumberField(TEXT("fx")); S.Fy = (*K)->GetNumberField(TEXT("fy"));
	S.Cx = (*K)->GetNumberField(TEXT("cx")); S.Cy = (*K)->GetNumberField(TEXT("cy"));
	S.IntrinsicsSource = Str(*K, TEXT("source"));
	const TArray<TSharedPtr<FJsonValue>> Rows = Arr(*Cam, TEXT("rotation"));
	const TArray<TSharedPtr<FJsonValue>> T = Arr(*Cam, TEXT("translation_mm"));
	if (Rows.Num() != 3 || T.Num() != 3) return;
	for (int32 i = 0; i < 3; ++i)
	{
		const TArray<TSharedPtr<FJsonValue>>& Row = Rows[i]->AsArray();
		for (int32 j = 0; j < 3 && j < Row.Num(); ++j) S.R[i][j] = Row[j]->AsNumber();
	}
	S.T = FVector3d(T[0]->AsNumber(), T[1]->AsNumber(), T[2]->AsNumber());
	for (const TSharedPtr<FJsonValue>& V : Arr(Json, TEXT("zones")))
	{
		const TSharedPtr<FJsonObject> O = V->AsObject();
		FYgoZone Z;
		Z.Player = Int(O, TEXT("player"));
		Z.Zone = Str(O, TEXT("zone"));
		for (const TSharedPtr<FJsonValue>& P : Arr(O, TEXT("polygon_mm"))) Z.Polygon.Add(Point(P));
		S.Zones.Add(MoveTemp(Z));
	}
	S.bValid = true;
	Scene = MoveTemp(S);
	UE_LOG(LogYgoLab, Display, TEXT("Scene: HFOV %.1f (%s), camera at %s mm, %d zones"),
		Scene.HorizontalFovDeg(), *Scene.IntrinsicsSource, *Scene.CameraCentreMm().ToString(), Scene.Zones.Num());
}

void UYgoLab::ParseDuel(const TSharedPtr<FJsonObject>& Json)
{
	FYgoDuel D;
	if (Json.IsValid())
	{
		D.bValid = true;
		Json->TryGetBoolField(TEXT("started"), D.bStarted);
		D.Turn = Int(Json, TEXT("turn"));
		D.Current = Int(Json, TEXT("current"));
		D.Phase = Str(Json, TEXT("phase"));
		const TSharedPtr<FJsonValue> Result = Raw(Json, TEXT("result"));  // text or an object: any value means it is over
		D.Result = !Result.IsValid() ? FString() : Result->Type == EJson::String ? Result->AsString() : FString(TEXT("over"));
		const TSharedPtr<FJsonObject>* Outcome;
		if (Json->TryGetObjectField(TEXT("result"), Outcome)) D.Winner = Int(*Outcome, TEXT("winner"), -1);
		for (const TSharedPtr<FJsonValue>& V : Arr(Json, TEXT("players")))
		{
			const TSharedPtr<FJsonObject> O = V->AsObject();
			FYgoPlayer P;
			P.Name = Str(O, TEXT("name")); P.Lp = Int(O, TEXT("lp"), 8000);
			P.Hand = Int(O, TEXT("hand")); P.Deck = Int(O, TEXT("deck")); P.ExtraDeck = Int(O, TEXT("extra_deck"));
			P.Graveyard = Int(O, TEXT("graveyard")); P.Banished = Int(O, TEXT("banished"));
			D.Players.Add(P);
		}
		for (const TSharedPtr<FJsonValue>& V : Arr(Json, TEXT("board")))
		{
			const TSharedPtr<FJsonObject> O = V->AsObject();
			FYgoBoardCard C;
			C.Player = Int(O, TEXT("player")); C.Zone = Str(O, TEXT("zone")); C.CopyId = Str(O, TEXT("copy_id"));
			C.CardId = Str(O, TEXT("card_id")); C.Name = Str(O, TEXT("name")); C.Position = Str(O, TEXT("position"));
			C.Controller = Int(O, TEXT("controller"), C.Player); C.Type = Str(O, TEXT("type"));
			C.RawCopyId = Raw(O, TEXT("copy_id"));
			D.Board.Add(C);
		}
		const TSharedPtr<FJsonObject>* Attack;
		if (Json->TryGetObjectField(TEXT("pending_attack"), Attack))
		{
			D.Attacker = Str(*Attack, TEXT("attacker")); D.Target = Str(*Attack, TEXT("target"));
		}
		const TSharedPtr<FJsonObject>* Preview;
		if (Json->TryGetObjectField(TEXT("battle_preview"), Preview))
		{
			D.bBattlePreview = true; D.BattleText = Str(*Preview, TEXT("text"));
			D.BattleOutcome = Str(*Preview, TEXT("outcome")); D.BattleProblem = Str(*Preview, TEXT("problem"));
		}
		for (const TSharedPtr<FJsonValue>& V : Arr(Json, TEXT("backs_seen")))
		{
			const TSharedPtr<FJsonObject> O = V->AsObject();
			D.BacksSeen.Add({Int(O, TEXT("player")), Str(O, TEXT("zone"))});
		}
		for (const TSharedPtr<FJsonValue>& V : Arr(Json, TEXT("recent")))
		{
			const TSharedPtr<FJsonObject> O = V->AsObject();
			FYgoPlay Play{Str(O, TEXT("id")), Str(O, TEXT("text")), Str(O, TEXT("card_id"))};
			Play.Alternatives = Options(O, TEXT("alternatives"));
			for (const TSharedPtr<FJsonValue>& W : Arr(O, TEXT("warnings"))) Play.Warnings.Add(W->AsString());
			D.Recent.Add(MoveTemp(Play));
		}
		for (const TSharedPtr<FJsonValue>& V : Arr(Json, TEXT("questions")))
		{
			const TSharedPtr<FJsonObject> O = V->AsObject();
			if (!O.IsValid()) continue;
			FYgoQuestion Q;
			Q.Key = Str(O, TEXT("key")); Q.Kind = Str(O, TEXT("kind")); Q.Player = Int(O, TEXT("player"));
			Q.Zone = Str(O, TEXT("zone")); Q.ZoneLabel = Str(O, TEXT("zone_label")); Q.CardName = Str(O, TEXT("card_name"));
			Q.CardId = Str(O, TEXT("card_id")); Q.Position = Str(O, TEXT("position")); Q.ExpectedPosition = Str(O, TEXT("expected_position"));
			Q.Hint = Str(O, TEXT("hint")); Q.Level = Int(O, TEXT("level"));
			Q.CopyId = Raw(O, TEXT("copy_id")); Q.ExpectedCopy = Raw(O, TEXT("expected_copy"));
			Q.Options = Options(O, TEXT("options"));
			D.Questions.Add(MoveTemp(Q));
		}
	}
	Duel = MoveTemp(D);
	OnDuel.Broadcast();
}

void UYgoLab::Act(const TSharedRef<FJsonObject>& Event, TFunction<void(const FString& Error)> Done)
{
	FString Body;
	FJsonSerializer::Serialize(Event, TJsonWriterFactory<>::Create(&Body));
	TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Req = FHttpModule::Get().CreateRequest();
	Req->SetURL(BaseUrl + TEXT("/duel"));
	Req->SetVerb(TEXT("POST"));
	Req->SetHeader(TEXT("Content-Type"), TEXT("application/json"));
	Req->SetContentAsString(Body);
	Req->SetTimeout(8.0f);
	TWeakObjectPtr<UYgoLab> Weak(this);
	Req->OnProcessRequestComplete().BindLambda([Weak, Done = MoveTemp(Done)](FHttpRequestPtr, FHttpResponsePtr Response, bool bOk)
	{
		UYgoLab* Self = Weak.Get();
		if (!Self) return;
		if (!bOk || !Response.IsValid()) { Done(TEXT("No se pudo hablar con el labo")); return; }
		TSharedPtr<FJsonObject> Json;
		FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Response->GetContentAsString()), Json);
		if (Response->GetResponseCode() != 200)
		{
			const FString Reason = Json.IsValid() ? Str(Json, TEXT("error")) : FString();
			Done(Reason.IsEmpty() ? FString::Printf(TEXT("El labo no lo aceptó (%d)"), Response->GetResponseCode()) : Reason);
			return;
		}
		const TSharedPtr<FJsonObject>* Duel;
		if (Json.IsValid() && Json->TryGetObjectField(TEXT("duel"), Duel)) Self->ParseDuel(*Duel);
		Done(FString());
	});
	Req->ProcessRequest();
}

FString UYgoLab::CardType(const FString& CardId)
{
	if (CardId.IsEmpty()) return FString();
	if (const TOptional<FSheet>* S = Sheets.Find(CardId)) return S->IsSet() ? S->GetValue().Type : FString();
	Sheets.Add(CardId);
	RequestJson(TEXT("/card-info?id=") + FGenericPlatformHttp::UrlEncode(CardId), [this, CardId](TSharedPtr<FJsonObject> Json, const FString&)
	{
		const FString Type = Json.IsValid() ? Str(Json, TEXT("card_type")) : FString();
		Sheets.Add(CardId, FSheet{Type.IsEmpty() ? FString(TEXT("?")) : Type, Json.IsValid() ? Str(Json, TEXT("name")) : FString()});
	});
	return FString();
}

FString UYgoLab::CardName(const FString& CardId)
{
	CardType(CardId);
	const TOptional<FSheet>* S = Sheets.Find(CardId);
	return S && S->IsSet() ? S->GetValue().Name : FString();
}

UTexture2D* UYgoLab::Sprite(const FYgoTrack& Track)
{
	// As the duel view: /cutout/<ref>, the close-up trimmed so its bottom row is the feet.
	if (Track.SpriteRef.IsEmpty()) return nullptr;
	return Png(Track.SpriteRef, TEXT("/cutout/") + FGenericPlatformHttp::UrlEncode(Track.SpriteRef));
}

UTexture2D* UYgoLab::Image(const FString& Path)
{
	return Png(Path, Path);
}

UTexture2D* UYgoLab::Png(const FString& Key, const FString& Path)
{
	if (TObjectPtr<UTexture2D>* T = Sprites.Find(Key)) return *T;
	if (SpritesRequested.Contains(Key)) return nullptr;
	SpritesRequested.Add(Key);
	TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Req = FHttpModule::Get().CreateRequest();
	Req->SetURL(BaseUrl + Path);
	Req->SetVerb(TEXT("GET"));
	TWeakObjectPtr<UYgoLab> Weak(this);
	Req->OnProcessRequestComplete().BindLambda([Weak, Key](FHttpRequestPtr, FHttpResponsePtr Response, bool bOk)
	{
		UYgoLab* Self = Weak.Get();
		if (!Self || !bOk || !Response.IsValid() || Response->GetResponseCode() != 200) return;
		if (UTexture2D* T = TextureFromPng(Response->GetContent())) Self->Sprites.Add(Key, T);
	});
	Req->ProcessRequest();
	return nullptr;
}

UTexture2D* UYgoLab::TextureFromPng(const TArray<uint8>& Png)
{
	TArray<uint8> Bgra; int32 W = 0, H = 0;
	if (!DecodeImage(EImageFormat::PNG, Png, Bgra, W, H)) return nullptr;
	UTexture2D* T = UTexture2D::CreateTransient(W, H, PF_B8G8R8A8);
	if (!T) return nullptr;
	FTexture2DMipMap& Mip = T->GetPlatformData()->Mips[0];
	void* Dest = Mip.BulkData.Lock(LOCK_READ_WRITE);
	FMemory::Memcpy(Dest, Bgra.GetData(), Bgra.Num());
	Mip.BulkData.Unlock();
	T->SRGB = true;
	T->AddressX = TA_Clamp; T->AddressY = TA_Clamp;
	T->UpdateResource();
	return T;
}
