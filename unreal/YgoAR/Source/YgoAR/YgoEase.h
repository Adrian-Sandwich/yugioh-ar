// The easing curves of web/duel.js (ease, span), so both views keep the same timing.
#pragma once

#include "CoreMinimal.h"

namespace YgoEase
{
	inline float Clamp01(float T) { return FMath::Clamp(T, 0.f, 1.f); }
	inline float Out(float T) { return 1 - FMath::Pow(1 - Clamp01(T), 3.f); }
	inline float In(float T) { return FMath::Pow(Clamp01(T), 3.f); }
	inline float Back(float T) { T = Clamp01(T); const float C = 1.9f; return 1 + (C + 1) * FMath::Pow(T - 1, 3.f) + C * FMath::Pow(T - 1, 2.f); }
	// Progress of T inside [A, B].
	inline float Span(float T, float A, float B) { return Clamp01((T - A) / (B - A)); }
}
