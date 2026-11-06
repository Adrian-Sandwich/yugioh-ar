#include "YgoTypes.h"

FVector3d FYgoScene::CameraCentreMm() const
{
	// C = -R^T t
	FVector3d C;
	for (int32 j = 0; j < 3; ++j)
		C[j] = -(R[0][j] * T.X + R[1][j] * T.Y + R[2][j] * T.Z);
	return C;
}

bool FYgoScene::ImageToTable(const FVector2D& Pixel, FVector2D& OutMm) const
{
	const FVector3d K((Pixel.X - Cx) / Fx, (Pixel.Y - Cy) / Fy, 1.0);
	FVector3d D;  // ray direction in world: R^T K^-1 [u v 1]
	for (int32 j = 0; j < 3; ++j)
		D[j] = R[0][j] * K.X + R[1][j] * K.Y + R[2][j] * K.Z;
	const FVector3d C = CameraCentreMm();
	if (FMath::Abs(D.Z) < 1e-9) return false;
	const double S = -C.Z / D.Z;
	if (S <= 0) return false;
	OutMm = FVector2D(C.X + S * D.X, C.Y + S * D.Y);
	return true;
}

const FYgoZone* FYgoScene::ZoneAt(const FVector2D& P) const
{
	for (const FYgoZone& Z : Zones)
	{
		bool bInside = false;
		const int32 N = Z.Polygon.Num();
		for (int32 i = 0, j = N - 1; i < N; j = i++)
		{
			const FVector2D& A = Z.Polygon[i];
			const FVector2D& B = Z.Polygon[j];
			if ((A.Y > P.Y) != (B.Y > P.Y) && P.X < (B.X - A.X) * (P.Y - A.Y) / (B.Y - A.Y) + A.X)
				bInside = !bInside;
		}
		if (bInside) return &Z;
	}
	return nullptr;
}

const FYgoZone* FYgoScene::FindZone(int32 Player, const FString& Zone) const
{
	return Zones.FindByPredicate([&](const FYgoZone& Z) { return Z.Player == Player && Z.Zone == Zone; });
}

bool FYgoScene::ZonePlace(const FYgoZone& Zone, FVector2D& OutCentre, float& OutCardWidth)
{
	const TArray<FVector2D>& P = Zone.Polygon;  // TL, TR, BR, BL of the zone on its player's mat
	if (P.Num() != 4) return false;
	OutCentre = (P[0] + P[1] + P[2] + P[3]) / 4;
	OutCardWidth = .72f * FVector2D::Distance((P[0] + P[3]) / 2, (P[1] + P[2]) / 2);
	return OutCardWidth > 5.f;
}
