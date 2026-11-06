#include "YgoParticles.h"

#include "Engine/StaticMesh.h"
#include "Materials/MaterialInterface.h"
#include "UObject/ConstructorHelpers.h"

UYgoParticles::UYgoParticles()
{
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Plane(TEXT("/Engine/BasicShapes/Plane.Plane"));
	if (Plane.Succeeded()) SetStaticMesh(Plane.Object);
	NumCustomDataFloats = 4;
	SetCollisionEnabled(ECollisionEnabled::NoCollision);
	CastShadow = false;
	SetMobility(EComponentMobility::Movable);
}

void UYgoParticles::Emit(const FYgoParticle& P)
{
	if (Live.Num() < MaxParticles) Live.Add(P);
}

void UYgoParticles::Step(float Dt, const FVector& CameraLocation)
{
	// GetMaterial(0) would give the plane's own lit material (black here, without lights): ask for ours.
	if (OverrideMaterials.IsEmpty() || !OverrideMaterials[0])
		if (UMaterialInterface* M = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/YgoAR/M_FxParticle.M_FxParticle"))) SetMaterial(0, M);

	TArray<FTransform> Transforms;
	TArray<float> Custom;
	Transforms.Reserve(Live.Num());
	Custom.Reserve(Live.Num() * 4);
	for (int32 i = Live.Num() - 1; i >= 0; --i)
	{
		FYgoParticle& P = Live[i];
		if (P.Delay > 0) { P.Delay -= Dt; continue; }
		P.Age += Dt;
		if (P.Age >= P.Life) { Live.RemoveAtSwap(i); continue; }
		P.Velocity.Z -= P.Gravity * Dt;
		P.Velocity *= FMath::Max(0.f, 1.f - P.Drag * Dt);
		P.Position += P.Velocity * Dt;
		const float T = P.Age / P.Life;
		// Fade in fast, out slow; sparks shrink as they cool.
		const float Alpha = FMath::Min(1.f, T * 12.f) * FMath::Square(1.f - T);
		const FVector ToCamera = (CameraLocation - P.Position).GetSafeNormal();
		const float Speed = P.Velocity.Size();
		FVector Along = FVector::VectorPlaneProject(P.Velocity, ToCamera);
		if (P.Stretch <= 0 || Along.IsNearlyZero()) Along = FVector::CrossProduct(ToCamera, FVector::UpVector);
		if (Along.IsNearlyZero()) Along = FVector::ForwardVector;
		// Plane mesh: 100 x 100 cm in its XY, facing +Z: Z at the camera, X along the motion.
		const FRotator Rotation = FRotationMatrix::MakeFromZX(ToCamera, Along).Rotator();
		const float Width = P.Size * (P.Stretch > 0 ? 1.f - .5f * T : 1.f);
		const float Length = P.Stretch > 0 ? Width + P.Stretch * Speed : Width;
		Transforms.Add(FTransform(Rotation, P.Position, FVector(Length / 100.f, Width / 100.f, 1.f)));
		Custom.Append({P.Color.R, P.Color.G, P.Color.B, Alpha * P.Color.A});
	}
	// Same count: move the instances; otherwise rebuild them.
	if (Transforms.Num() == Shown && Shown > 0)
		BatchUpdateInstancesTransforms(0, Transforms, true, false, true);
	else
	{
		ClearInstances();
		if (Transforms.Num()) AddInstances(Transforms, false, true);
		Shown = Transforms.Num();
	}
	for (int32 i = 0; i < Shown; ++i)
		SetCustomData(i, TArrayView<const float>(Custom.GetData() + i * 4, 4), false);
	MarkRenderStateDirty();
}
