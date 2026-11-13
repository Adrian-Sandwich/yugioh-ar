"""Materials of the YgoAR project, built by script so they live in git as text (Content/ is generated).

Run inside the editor, headless:
    UnrealEditor-Cmd.exe <path>/YgoAR.uproject -run=pythonscript -script=<path>/Scripts/make_assets.py -unattended -nosplash

Each effect is one Custom (HLSL) node: the look is readable and diffable here. Colours arrive as
parameters from C++ (the duel view's palette, web/duel.js RGB) and come out in HDR, so bloom picks
up the light and leaves the video alone (bloom threshold 1, AYgoTableView).
"""
import os

import unreal

ROOT = '/Game/YgoAR'
mel = unreal.MaterialEditingLibrary
assets = unreal.EditorAssetLibrary
DEFAULT_TEXTURE = '/Engine/EngineResources/DefaultTexture.DefaultTexture'

# --- HLSL -------------------------------------------------------------------------------------

MAGIC = r'''
// Mode 0: summon circle (rings, ticks, runes and a hexagram drawn on by Progress); also a spell's.
// Mode 1: a monster's base ring with two arcs chasing each other. Mode 2: shockwave.
// Mode 3: a trap springing: a hexagon snaps shut and six chains whip out (Progress = its time).
// Mode 4: a trap's base, two hexagons. Mode 5: a card set face-down: three spiral arms closing in.
// Mode 6: a soft glow. Mode 7: a zone's four corners (the plane is the zone; Span is its width / height).
// Modes 3-5 are drawn in web/duel.js's plane units (onPlane: 1 = 0.44 card
// widths), Span of them from the centre to the plane's edge.
const float TAU = 6.2831853, PI = 3.1415927;
float2 p = UV * 2.0 - 1.0;
float r = length(p);
float a = atan2(p.y, p.x);
float w = max(fwidth(r) * 1.5, 0.002);
float3 white = float3(1, 1, 1);
float3 col = 0;
float2 q = p * Span;
float rq = r * Span, wq = w * Span;
// Distance to a hexagon with vertices at 30 + 60k degrees, as its apothem (its sides face 0, 60, ...).
float hd = 0;
for (int s = 0; s < 6; s++) hd = max(hd, dot(q, float2(cos(s * TAU / 6.0), sin(s * TAU / 6.0))));
if (Mode < 0.5)
{
    float rot = Time * 0.35 + Seed;
    float sweep = smoothstep(0.0, 0.02, saturate(Progress / 0.3) - frac(a / TAU + 0.25));
    float outer = 1 - smoothstep(0.014, 0.014 + w, abs(r - 0.95));
    float ring2 = 1 - smoothstep(0.006, 0.006 + w, abs(r - 0.86));
    float ring3 = 1 - smoothstep(0.008, 0.008 + w, abs(r - 0.58));
    float tk = frac(a / TAU * 64.0 + rot * 2.0);
    float ticks = step(0.86, r) * step(r, 0.95) * (1 - smoothstep(0.12, 0.17, abs(tk - 0.5)));
    // Runes: 20 cells turning the other way, each a few strokes chosen by a hash of the cell.
    float qr = (r - 0.64) / 0.16;
    float ca = a / TAU * 20.0 - rot * 1.5;
    float cell = floor(ca), u = frac(ca);
    float h1 = frac(sin(cell * 12.9898 + Seed * 3.1) * 43758.5453);
    float h2 = frac(sin(cell * 78.233 + Seed * 1.7) * 24634.6345);
    float lw = 0.07, g = 0;
    g = max(g, (1 - smoothstep(lw, lw + 0.04, abs(u - 0.5))) * step(0.3, h1));
    g = max(g, (1 - smoothstep(lw, lw + 0.04, abs(qr - 0.5))) * step(h2, 0.6) * step(0.2, u) * step(u, 0.8));
    g = max(g, (1 - smoothstep(lw, lw + 0.04, abs(qr - 0.15))) * step(0.5, h2) * step(0.15, u) * step(u, 0.85));
    g = max(g, (1 - smoothstep(lw, lw + 0.04, abs(qr - 0.85))) * step(h1, 0.7) * step(0.15, u) * step(u, 0.85));
    g = max(g, (1 - smoothstep(0.1, 0.16, length(float2(u - 0.5, qr - 0.5)))) * step(0.8, h1));
    float runes = g * step(0.0, qr) * step(qr, 1.0) * step(0.12, u) * step(u, 0.88);
    // Hexagram: two triangles inscribed in the inner ring, turning slowly.
    float R = 0.58, m1 = -1e3, m2 = -1e3;
    for (int k = 0; k < 3; k++)
    {
        float t1 = rot * 0.6 + k * TAU / 3.0;
        m1 = max(m1, r * cos(a - t1));
        m2 = max(m2, r * cos(a - t1 - TAU / 6.0));
    }
    float hex = max(1 - smoothstep(0.012, 0.012 + w, abs(m1 - R * 0.5)), 1 - smoothstep(0.012, 0.012 + w, abs(m2 - R * 0.5))) * step(r, R + 0.01);
    float lines = (outer + ring2 * 0.8 + ticks * 0.7) * sweep + ring3 * 0.8 * saturate(Progress * 5)
                + runes * 0.9 * saturate((Progress - 0.12) * 6) + hex * saturate((Progress - 0.18) * 6);
    float fill = exp(-r * 2.5) * 0.25 * saturate(Progress * 4);
    col = Color.rgb * (lines + fill) + white * lines * 0.12;
}
else if (Mode < 1.5)
{
    float t = Time * 1.1 + Seed;
    float ring = 1 - smoothstep(0.02, 0.02 + w, abs(r - 0.9));
    float arcs = (pow(saturate(cos(a - t)), 24) + pow(saturate(cos(a - t - 3.14159)), 24)) * (1 - smoothstep(0.035, 0.035 + w, abs(r - 0.9)));
    float pool = (1 - smoothstep(0.0, 0.9, r)) * 0.18;
    col = Color.rgb * (ring * 0.55 + arcs * 1.6 + pool) + white * arcs * 0.15;
}
else if (Mode < 2.5)
{
    float ring = exp(-pow((r - 0.85) / 0.07, 2));
    float inner = smoothstep(0.85, 0.2, r) * 0.12;
    col = Color.rgb * (ring * 1.4 + inner) + white * ring * 0.15;
}
else if (Mode < 3.5)
{
    float t = saturate(Progress);
    float u = saturate(t / 0.3) - 1, back = 1 + 2.9 * u * u * u + 1.9 * u * u;
    float size = 1.5 - 0.45 * back;
    float hex = 1 - smoothstep(0.063, 0.063 + wq, abs(hd - size * 0.8660254));
    float o = 1 - saturate((t - 0.1) / 0.4), len = 1.2 + 1.3 * (1 - o * o * o);
    float aq = atan2(q.y, q.x), chains = 0;
    for (int k = 0; k < 6; k++)
    {
        // Each chain wavers along its length and is dashed into links.
        float d = aq - (k * TAU / 6.0 + 0.3 + sin(rq / len * 7.2 + t * 8.0) * 0.08);
        d -= TAU * floor((d + PI) / TAU);
        float dist = abs(d) < 1.5 ? rq * abs(sin(d)) : 1e3;
        float link = step(frac(rq / 0.4147), 0.609);
        chains = max(chains, (1 - smoothstep(0.044, 0.044 + wq, dist)) * link * step(rq, len));
    }
    col = Color.rgb * (hex + chains * 0.9) + white * (hex + chains) * 0.12;
}
else if (Mode < 4.5)
{
    float h1 = 1 - smoothstep(0.04, 0.04 + wq, abs(hd - 1.05 * 0.8660254));
    float h2 = 1 - smoothstep(0.04, 0.04 + wq, abs(hd - 0.78 * 0.8660254));
    col = Color.rgb * (h1 + h2 * 0.5) + white * h1 * 0.1;
}
else if (Mode < 5.5)
{
    float o = 1 - saturate(Progress), R = 1.4 - 1.2 * (1 - o * o * o);
    float aq = atan2(q.y, q.x), arms = 0;
    for (int k = 0; k < 3; k++)
    {
        // Arm k: angle Time + 2.1 k + 0.18 j at radius R (1 - j / 30), j from 0 to 24.
        float j = 30 * (1 - rq / R);
        float d = aq - (Time * 3.333 + k * 2.1 + 0.18 * j);
        d -= TAU * floor((d + PI) / TAU);
        arms = max(arms, (1 - smoothstep(0.038, 0.038 + wq, rq * abs(d))) * step(0, j) * step(j, 24));
    }
    col = Color.rgb * arms + white * arms * 0.12;
}
else if (Mode < 6.5)
{
    float g = saturate(1 - r);
    g *= g;
    col = Color.rgb * g * 0.8 + white * g * g * g * 0.3;
}
else
{
    float2 e = 1 - abs(p);                         // to the edges, in half-sizes
    float2 thick = float2(0.045 / Span, 0.045);    // the same on both axes
    float2 reach = float2(0.3 / Span, 0.3);
    float corners = max(step(e.x, thick.x) * step(e.y, reach.y), step(e.y, thick.y) * step(e.x, reach.x));
    col = Color.rgb * corners + white * corners * 0.15;
    return col * Intensity * Alpha;
}
return col * Intensity * Alpha * step(r, 1.0);
'''

BEAM = r'''
// Pillar of light on the engine's 100 cm cylinder (pivot at its centre): bright where it faces the
// camera, streaks rising, fading to nothing at the top.
float h = saturate(LocalPos.z / 100.0 + 0.5);
float facing = abs(dot(normalize(N), normalize(V)));
float core = pow(facing, 2.5);
float edge = pow(1 - facing, 3.0) * 0.35;
float ang = atan2(LocalPos.y, LocalPos.x);
float n = 0.5 + 0.5 * sin(h * 26.0 - Time * 9.0 + sin(ang * 3.0 + Seed) * 2.0);
float n2 = 0.5 + 0.5 * sin(h * 11.0 - Time * 5.0 + ang * 2.0);
float fade = pow(1 - h, 1.6) * smoothstep(0.0, 0.04, h);
float3 col = Color.rgb * (core * (0.6 + 0.4 * n) + edge + 0.25 * n2 * core) + float3(1, 1, 1) * pow(core, 4.0) * 0.3 * (0.7 + 0.3 * n);
return col * fade * Alpha * Intensity;
'''

PARTICLE = r'''
float d = length(UV * 2.0 - 1.0);
float s = saturate(1.0 - d);
s = s * s * (3.0 - 2.0 * s);
return float3(R, G, B) * s * A;
'''

SPRITE = r'''
// The cut-out with a halo of its owner's colour (its silhouette, widened, only outside it), faint
// scanlines, and a white flash when it appears. Output: colour and opacity.
// The quad is SpritePad (AYgoStage) times the cut-out, so the halo has room around it; nothing is
// read outside the cut-out (the texture wraps). Automatic cut-outs keep a faint veil where the
// background was (alpha up to ~0.06): cut below 0.08.
#define CUT(a) saturate(((a) - 0.08) / 0.92)
#define TAP(t) (CUT(Texture2DSample(Tex, TexSampler, t).a) * all(t == saturate(t)))
float2 uv = (UV - 0.5) * 1.12 + 0.5;
float4 c = Texture2DSample(Tex, TexSampler, uv);
c.a = TAP(uv);
float halo = 0;
for (int i = 0; i < 12; i++)
{
    float ang = i * 0.5235988;
    float2 o = float2(cos(ang), sin(ang));
    float2 t1 = uv + o * 0.025, t2 = uv + o * 0.05;
    halo += TAP(t1) + TAP(t2) * 0.6;
}
halo = saturate(halo / 19.2) * (1 - c.a);
float scan = 1 + 0.05 * sin(uv.y * 420.0 + Time * 6.0);
float op = saturate(c.a + halo * 0.55);
float3 col = c.rgb * c.a * (1 + Flash * 1.2) * scan + Flash * 0.6 * c.a + Glow.rgb * 2.0 * halo * 0.55;
col /= max(op, 1e-3);
return float4(col, op * Alpha);
'''

SHADOW = r'''
float r = length(UV * 2.0 - 1.0);
return Alpha * pow(saturate(1.0 - r), 1.5);
'''

SHIELD = r'''
// Defense Position: a translucent hexagon in front of the monster (pointy top, a little flat), its
// light rim and a highlight sweeping across it (web/duel.js drawMonster). Output: colour and opacity.
float2 p = UV * 2.0 - 1.0;
float2 q = float2(p.x, p.y / 0.9);
float hd = 0;
for (int k = 0; k < 6; k++) hd = max(hd, dot(q, float2(cos(k * 1.0471976), sin(k * 1.0471976))));
float apo = 0.8660254 * 0.95, w = max(fwidth(hd) * 1.5, 0.004);
float inside = 1 - smoothstep(apo - w, apo, hd);
float rim = 1 - smoothstep(0.035, 0.035 + w, abs(hd - apo));
float g = saturate((p.x + p.y) * 0.25 + 0.5);
float fa = lerp(0.18, 0.32, g);
float3 fill = lerp(float3(0.102, 0.402, 1.0), float3(0.021, 0.102, 0.578), g);
float sweep = frac(Time / 1.6 + Seed) * 4.0 - 2.0;
float hl = saturate(1 - abs(p.x - sweep) / 0.3) * 0.35 * inside;
float op = saturate(inside * (fa + hl) + rim * 0.85);
float3 col = fill * fa * inside + float3(0.716, 0.871, 1.0) * hl + float3(0.305, 0.61, 1.0) * rim * 1.3;
return float4(col / max(op, 1e-3), op * Alpha);
'''

SHARD = r'''
// One of the 6 x 6 pieces of a destroyed monster's cut-out (web/duel.js 'destroy'): its cell of the
// sprite, glowing orange (#ff9a3c) while it breaks. Per instance: the cell (Q, R), Alpha and Hot.
float2 uv = (UV + float2(Q, R)) / 6.0;
float4 c = Texture2DSample(Tex, TexSampler, uv);
float a = saturate((c.a - 0.08) / 0.92);
return float4(c.rgb + Hot * float3(1.0, 0.33, 0.045) * 0.7, a * Alpha);
'''

PLATE = r'''
// The HUD's one material: lapis lacquer in a gold rim, the pairing of the Millennium shield and of the
// Egyptian pieces it comes from. It is a rounded rectangle's distance field in half-heights of the
// widget (Aspect = width / height). The rim is a bevel lit from the top left, a thin inlay of Accent
// runs inside it, Lit warms the plate (a hovered button, the player on turn), and Sheen sweeps one
// glint across it (0 to 1, when life points change). Knot (+1 right, -1 left) ties the plate off
// with a bar, which makes it a cartouche. Body is the lacquer's opacity. Output: colour and opacity.
float2 p = (UV - 0.5) * 2.0 * float2(Aspect, 1.0);
float end = abs(Knot) > 0.5 ? 0.26 : 0.0;
float side = Knot > 0.0 ? 1.0 : -1.0;
float2 c = p + float2(side * end * 0.5, 0.0);
float2 q = abs(c) - float2(Aspect - end * 0.5 - Radius, 1.0 - Radius);
float d = length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - Radius;
if (end > 0.0)
{
    float2 b = abs(p - float2(side * (Aspect - 0.075), 0.0)) - float2(0.075, 0.74);
    d = min(d, length(max(b, 0.0)) + min(max(b.x, b.y), 0.0));
}
float w = max(fwidth(d), 1e-4);
float inside = 1.0 - smoothstep(-w, 0.0, d);
float2 g = float2(ddx(d), ddy(d));
float2 n = g / max(length(g), 1e-5);
float t = saturate(-d / Rim);
float light = dot(n, float2(-0.55, -0.83)) * cos(t * 3.1415927);
float3 gold = float3(0.80, 0.55, 0.20) * (0.72 + 0.62 * light) + float3(1.0, 0.85, 0.55) * pow(saturate(light), 5.0) * 0.55;
float3 lacquer = Fill.rgb * lerp(1.45, 0.7, saturate(UV.y));
lacquer = lerp(lacquer, Accent.rgb, Lit * 0.35);
float inlay = 1.0 - smoothstep(w * 0.6, w * 1.7, abs(-d - Rim * 1.55));
lacquer = lerp(lacquer, Accent.rgb, inlay * 0.75);
float rim = 1.0 - smoothstep(Rim - w, Rim, -d);
float3 col = lerp(lacquer, gold, rim);
float s = (p.x + p.y * 0.6) / Aspect;
col += float3(1.0, 0.92, 0.75) * saturate(1.0 - abs(s - lerp(-1.5, 1.5, Sheen)) / 0.16) * step(0.001, Sheen) * step(Sheen, 0.999) * 0.5;
return float4(col, inside * lerp(Body, 1.0, rim) * Alpha);
'''

METAL = r'''
// A face-down monster's Millennium shield as a solid thing (AYgoStage builds its mesh): its two
// drawings as the colour, and their relief maps (tools/make_shield_relief.py: normal x and y, how
// metallic, height) for the light. The scene has no lights (the video must come out as filmed), so
// the light is worked out here: one key light, and a made-up room to reflect (a bright ceiling, a
// dark floor, a soft band that only metal picks up), which is what makes gold read as gold when it turns. Vertex colour:
// red on the edge between the two faces, green on the back face. AxisX/Y/Z are the shield's right,
// down and front in the world. Output: colour (HDR: the glints bloom).
const float PI = 3.1415927;
float wall = step(0.5, VC.r), rear = step(0.5, VC.g);
float2 uv = rear > 0.5 ? float2(1 - UV.x, UV.y) : UV;
float4 art = lerp(Texture2DSample(ArtFront, ArtFrontSampler, uv), Texture2DSample(ArtBack, ArtBackSampler, uv), rear);
float4 rel = lerp(Texture2DSample(ReliefFront, ReliefFrontSampler, uv), Texture2DSample(ReliefBack, ReliefBackSampler, uv), rear);
const float3 gold = float3(0.78, 0.38, 0.06);
float covered = saturate(art.a * 1.5);
float3 base = lerp(gold, art.rgb, covered);
float metal = lerp(1.0, rel.b, covered);
float2 n2 = (rel.rg * 2.0 - 1.0) * Relief;
float side = rear > 0.5 ? -1.0 : 1.0;
float3 nl = normalize(float3(n2, 1.0));
float3 N = normalize(AxisX.rgb * nl.x * side + AxisY.rgb * nl.y + AxisZ.rgb * nl.z * side);
if (wall > 0.5)
{
    // The edge faces outward, where the bevel's normal already leans; a little toward the nearer face.
    float2 o = rel.rg * 2.0 - 1.0;
    o = o / max(length(o), 0.05);
    N = normalize(AxisX.rgb * o.x + AxisY.rgb * o.y + AxisZ.rgb * 0.2 * side);
    base = gold; metal = 1.0;
}
float3 Vn = normalize(V);
if (dot(N, Vn) < 0.0) N = reflect(N, Vn);   // a normal bent away from the eye: no black rims
float3 L = normalize(Light.rgb);
float3 H = normalize(L + Vn);
float ndl = saturate(dot(N, L)), ndh = saturate(dot(N, H)), ndv = saturate(dot(N, Vn));
float rough = lerp(0.5, 0.26, metal);
float a2 = rough * rough * rough * rough;
float d = ndh * ndh * (a2 - 1.0) + 1.0;
float spec = a2 / (PI * d * d) * 0.25 * ndl;
float3 R = reflect(-Vn, N);
// The room: ceiling over floor, the key light's panel, and a band that sweeps across the metal as it turns.
float room = lerp(0.10, 0.85, smoothstep(-0.35, 0.55, R.z));
room += 1.6 * pow(saturate(dot(R, L)), 10.0);
float band = 0.5 + 0.5 * sin(R.x * 2.3 + R.y * 1.4 + 0.6);
room += 0.45 * band * band * band * metal * metal * smoothstep(-0.2, 0.4, R.z);
float fres = pow(1.0 - ndv, 5.0) * 0.35;   // metal turned edge-on brightens, it does not go white
float3 F0 = lerp(float3(0.04, 0.04, 0.04), base, metal);
float3 F = F0 + (1.0 - F0) * fres;
float cavity = 0.72 + 0.28 * rel.a;
float3 col = base * (1.0 - metal) * (0.42 + 0.68 * ndl) + base * metal * 0.22;
col += F * (room * lerp(0.3, 1.0, metal) + spec * 2.2);
col *= cavity;
col += Flash * float3(1.0, 0.82, 0.5);
return col;
'''

# --- building blocks --------------------------------------------------------------------------


def new_material(name, blend, two_sided=True, instanced=False):
    path = f'{ROOT}/{name}'
    if assets.does_asset_exist(path):
        assets.delete_asset(path)
    m = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, ROOT, unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_UNLIT)
    m.set_editor_property('blend_mode', blend)
    m.set_editor_property('two_sided', two_sided)
    if instanced:
        m.set_editor_property('used_with_instanced_static_meshes', True)
    return m


def node(m, cls, x, y, **props):
    e = mel.create_material_expression(m, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def scalar(m, name, value, y):
    return node(m, unreal.MaterialExpressionScalarParameter, -900, y, parameter_name=name, default_value=value)


def vector(m, name, value, y):
    return node(m, unreal.MaterialExpressionVectorParameter, -900, y, parameter_name=name, default_value=unreal.LinearColor(*value))


def custom(m, code, output_type, inputs):
    """A Custom node fed by (name, expression) pairs."""
    c = node(m, unreal.MaterialExpressionCustom, -400, 0, code=code, output_type=output_type)
    pins = []
    for name, _ in inputs:
        pin = unreal.CustomInput()
        pin.set_editor_property('input_name', name)
        pins.append(pin)
    c.set_editor_property('inputs', pins)
    for name, source in inputs:
        mel.connect_material_expressions(source, '', c, name)
    return c


def colour_and_opacity(m, c):
    """A float4 Custom node's rgb to the emissive colour and its alpha to the opacity."""
    rgb = node(m, unreal.MaterialExpressionComponentMask, -150, -50, r=True, g=True, b=True, a=False)
    alpha = node(m, unreal.MaterialExpressionComponentMask, -150, 50, r=False, g=False, b=False, a=True)
    mel.connect_material_expressions(c, '', rgb, '')
    mel.connect_material_expressions(c, '', alpha, '')
    mel.connect_material_property(rgb, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.connect_material_property(alpha, '', unreal.MaterialProperty.MP_OPACITY)


def texture(m, name, y):
    return node(m, unreal.MaterialExpressionTextureObjectParameter, -900, y, parameter_name=name, texture=unreal.load_asset(DEFAULT_TEXTURE))


def finish(m):
    mel.recompile_material(m)
    assets.save_loaded_asset(m)
    unreal.log(f'YgoAR: {m.get_path_name()}')


# --- materials --------------------------------------------------------------------------------


def video():
    m = new_material('M_Video', unreal.BlendMode.BLEND_OPAQUE, two_sided=False)
    t = node(m, unreal.MaterialExpressionTextureSampleParameter2D, -500, 0, parameter_name='Video',
             texture=unreal.load_asset(DEFAULT_TEXTURE))
    mel.connect_material_property(t, 'RGB', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    finish(m)


def magic():
    m = new_material('M_FxMagic', unreal.BlendMode.BLEND_ADDITIVE)
    c = custom(m, MAGIC, unreal.CustomMaterialOutputType.CMOT_FLOAT3, [
        ('UV', node(m, unreal.MaterialExpressionTextureCoordinate, -900, -300)),
        ('Color', vector(m, 'Color', (0.1, 0.9, 1.0, 1), -200)),
        ('Alpha', scalar(m, 'Alpha', 1.0, -100)),
        ('Progress', scalar(m, 'Progress', 1.0, 0)),
        ('Mode', scalar(m, 'Mode', 0.0, 100)),
        ('Seed', scalar(m, 'Seed', 0.0, 200)),
        ('Intensity', scalar(m, 'Intensity', 1.4, 300)),
        ('Span', scalar(m, 'Span', 1.0, 350)),
        ('Time', node(m, unreal.MaterialExpressionTime, -900, 400)),
    ])
    mel.connect_material_property(c, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    finish(m)


def beam():
    m = new_material('M_FxBeam', unreal.BlendMode.BLEND_ADDITIVE)
    c = custom(m, BEAM, unreal.CustomMaterialOutputType.CMOT_FLOAT3, [
        ('LocalPos', node(m, unreal.MaterialExpressionLocalPosition, -900, -400)),
        ('N', node(m, unreal.MaterialExpressionVertexNormalWS, -900, -300)),
        ('V', node(m, unreal.MaterialExpressionCameraVectorWS, -900, -250)),
        ('Color', vector(m, 'Color', (0.1, 0.9, 1.0, 1), -200)),
        ('Alpha', scalar(m, 'Alpha', 1.0, -100)),
        ('Seed', scalar(m, 'Seed', 0.0, 0)),
        ('Intensity', scalar(m, 'Intensity', 1.5, 100)),
        ('Time', node(m, unreal.MaterialExpressionTime, -900, 200)),
    ])
    mel.connect_material_property(c, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    finish(m)


def particle():
    m = new_material('M_FxParticle', unreal.BlendMode.BLEND_ADDITIVE, instanced=True)
    data = [(k, node(m, unreal.MaterialExpressionPerInstanceCustomData, -900, i * 100, data_index=i)) for i, k in enumerate('RGBA')]
    c = custom(m, PARTICLE, unreal.CustomMaterialOutputType.CMOT_FLOAT3,
               [('UV', node(m, unreal.MaterialExpressionTextureCoordinate, -900, -200))] + data)
    mel.connect_material_property(c, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    finish(m)


def sprite():
    m = new_material('M_FxSprite', unreal.BlendMode.BLEND_TRANSLUCENT)
    c = custom(m, SPRITE, unreal.CustomMaterialOutputType.CMOT_FLOAT4, [
        ('UV', node(m, unreal.MaterialExpressionTextureCoordinate, -900, -300)),
        ('Tex', texture(m, 'Sprite', -200)),
        ('Alpha', scalar(m, 'Alpha', 1.0, -100)),
        ('Flash', scalar(m, 'Flash', 0.0, 0)),
        ('Glow', vector(m, 'Glow', (0.1, 0.9, 1.0, 1), 100)),
        ('Time', node(m, unreal.MaterialExpressionTime, -900, 200)),
    ])
    colour_and_opacity(m, c)
    finish(m)


def shield():
    m = new_material('M_FxShield', unreal.BlendMode.BLEND_TRANSLUCENT)
    c = custom(m, SHIELD, unreal.CustomMaterialOutputType.CMOT_FLOAT4, [
        ('UV', node(m, unreal.MaterialExpressionTextureCoordinate, -900, -300)),
        ('Alpha', scalar(m, 'Alpha', 1.0, -100)),
        ('Seed', scalar(m, 'Seed', 0.0, 0)),
        ('Time', node(m, unreal.MaterialExpressionTime, -900, 100)),
    ])
    colour_and_opacity(m, c)
    finish(m)


def shard():
    m = new_material('M_FxShard', unreal.BlendMode.BLEND_TRANSLUCENT, instanced=True)
    data = [(k, node(m, unreal.MaterialExpressionPerInstanceCustomData, -900, i * 100, data_index=i)) for i, k in enumerate(('Q', 'R', 'Alpha', 'Hot'))]
    c = custom(m, SHARD, unreal.CustomMaterialOutputType.CMOT_FLOAT4,
               [('UV', node(m, unreal.MaterialExpressionTextureCoordinate, -900, -300)), ('Tex', texture(m, 'Sprite', -200))] + data)
    colour_and_opacity(m, c)
    finish(m)


def ui_plate():
    m = new_material('M_UiPlate', unreal.BlendMode.BLEND_TRANSLUCENT)
    m.set_editor_property('material_domain', unreal.MaterialDomain.MD_UI)
    c = custom(m, PLATE, unreal.CustomMaterialOutputType.CMOT_FLOAT4, [
        ('UV', node(m, unreal.MaterialExpressionTextureCoordinate, -900, -300)),
        ('Aspect', scalar(m, 'Aspect', 3.0, -200)),
        ('Radius', scalar(m, 'Radius', 0.5, -150)),
        ('Rim', scalar(m, 'Rim', 0.14, -100)),
        ('Knot', scalar(m, 'Knot', 0.0, -50)),
        ('Body', scalar(m, 'Body', 0.92, 0)),
        ('Fill', vector(m, 'Fill', (0.008, 0.025, 0.11, 1), 50)),
        ('Accent', vector(m, 'Accent', (0.80, 0.55, 0.20, 1), 100)),
        ('Lit', scalar(m, 'Lit', 0.0, 150)),
        ('Sheen', scalar(m, 'Sheen', 0.0, 200)),
        ('Alpha', scalar(m, 'Alpha', 1.0, 250)),
    ])
    colour_and_opacity(m, c)
    finish(m)


def metal():
    if assets.does_asset_exist(f'{ROOT}/M_FxCoin'):
        assets.delete_asset(f'{ROOT}/M_FxCoin')  # the flat shield this one replaced
    m = new_material('M_FxMetal', unreal.BlendMode.BLEND_OPAQUE)
    c = custom(m, METAL, unreal.CustomMaterialOutputType.CMOT_FLOAT3, [
        ('UV', node(m, unreal.MaterialExpressionTextureCoordinate, -900, -600)),
        ('VC', node(m, unreal.MaterialExpressionVertexColor, -900, -500)),
        ('V', node(m, unreal.MaterialExpressionCameraVectorWS, -900, -400)),
        ('ArtFront', texture(m, 'ArtFront', -300)),
        ('ArtBack', texture(m, 'ArtBack', -200)),
        ('ReliefFront', texture(m, 'ReliefFront', -100)),
        ('ReliefBack', texture(m, 'ReliefBack', 0)),
        ('AxisX', vector(m, 'AxisX', (1, 0, 0, 0), 100)),
        ('AxisY', vector(m, 'AxisY', (0, 1, 0, 0), 200)),
        ('AxisZ', vector(m, 'AxisZ', (0, 0, 1, 0), 300)),
        ('Light', vector(m, 'Light', (-0.4, -0.5, 0.75, 0), 400)),
        ('Relief', scalar(m, 'Relief', 1.0, 500)),
        ('Flash', scalar(m, 'Flash', 0.0, 600)),
    ])
    mel.connect_material_property(c, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    finish(m)


def shadow():
    m = new_material('M_FxShadow', unreal.BlendMode.BLEND_TRANSLUCENT)
    c = custom(m, SHADOW, unreal.CustomMaterialOutputType.CMOT_FLOAT1, [
        ('UV', node(m, unreal.MaterialExpressionTextureCoordinate, -900, -100)),
        ('Alpha', scalar(m, 'Alpha', 0.45, 0)),
    ])
    black = node(m, unreal.MaterialExpressionConstant3Vector, -150, -100, constant=unreal.LinearColor(0, 0, 0, 1))
    mel.connect_material_property(black, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.connect_material_property(c, '', unreal.MaterialProperty.MP_OPACITY)
    finish(m)


def audio():
    """The sounds in Audio/ (CC0, see its LICENSE.txt) become /Game/YgoAR/Audio/S_<name>."""
    folder = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()) + 'Audio'
    tasks = []
    for name in sorted(n for n in os.listdir(folder) if n.endswith('.ogg')):
        task = unreal.AssetImportTask()
        task.set_editor_property('filename', os.path.join(folder, name))
        task.set_editor_property('destination_path', ROOT + '/Audio')
        task.set_editor_property('destination_name', 'S_' + name[:-4])
        task.set_editor_property('automated', True)
        task.set_editor_property('replace_existing', True)
        task.set_editor_property('save', True)
        tasks.append(task)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)


for build in (video, magic, beam, particle, sprite, shadow, shield, shard, metal, ui_plate, audio):
    build()
