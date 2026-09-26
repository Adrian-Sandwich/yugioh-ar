# Contributing

*[Versión en español](CONTRIBUTING.es.md)*

Thanks for wanting to help. This project aims at a real-time augmented reality
duel engine for Yu-Gi-Oh!, and it still has a long way to go. There is work
for people who code and for people who do not.

## Without coding

**Photos of real cards.** This is what is missing most. Photos of one or
several cards on a table, taken with a phone, in any of these languages:
Spanish, English, German, French, Portuguese. Variety that helps: with and
without sleeves, with glare or shadow, rotated cards, two copies of the same
card, rare or foil cards, and also cards that are **not** Yu-Gi-Oh! (they
serve as negatives).

How to deliver them:

1. If you have the project running, open http://127.0.0.1:8768/capture,
   upload the photo and mark the four corners of each card and its identity.
   Then share the contents of `data/pilot/captures/`.
2. If not, open an issue with the photos attached or a link, and state the
   language and conditions. Someone else will annotate them.

Do not upload photos with visible personal data. By sharing them you accept
that they will be used to train and evaluate this project.

**Testing on your hardware.** Follow [ENTREGA_PILOTO.md](research/ENTREGA_PILOTO.md)
(Spanish) to start the viewer on your PC with your camera, and report what
happened in an issue: OS, Python, camera, what was recognized and what was
not, and the JSON files the tests leave in `research/qa/`.

**Reviewing the catalog.** The gallery at http://127.0.0.1:8768 shows proposed
artwork references that need to be approved or corrected. Decisions are saved
in `data/catalog/reviews.sqlite`; share that file.

## Coding

Open areas, from most to least urgent:

- Training the four-corner detector (YOLO11) on real data and contrastive
  fine-tuning of the embeddings. The experiments are already designed in
  [COLA_EXPERIMENTOS.md](research/COLA_EXPERIMENTOS.md); a GPU is needed.
- Tracking with optical flow and a moving camera.
- Isolating ONNX inference in a recoverable process.
- Duel rules engine: zones, phases, life points. It is independent from
  recognition and can be started from scratch, in Python or another language.
- 3D AR layer with clearly licensed models.
- Lower latency: warp limited to the region of interest, batching, pose
  export to ONNX.

Before starting something big, open an issue to agree on the approach. The
[consolidated status](research/TRANSFERENCIA_GENERAL.md) and the
[current plan](research/PLAN_MEJORA_INTEGRAL.md) explain what has already been
decided and why.

## House rules

These are the rules the project has followed since day one. Keeping them is
what lets a third party trust what the repository says.

1. **Every change says what was tested and what was not.** A pull request
   describes the test that backs it (`qa_*.py`, JSON report in `research/qa/`)
   and its limits. If something was not measured, say so.
2. **No numbers are claimed that were not measured.** A time observed under
   load is not a benchmark; a test with two photos is not an accuracy rate.
3. **Identity, artwork and physical copy are different things.** `card_id`,
   `artwork_id` and `track_id` are never mixed.
4. **OCR is evidence, not truth.** It never guesses characters or overwrites
   the visual identity. Ambiguities are kept.
5. **Regenerable data lives apart from human decisions.** Nothing rebuilt
   automatically may overwrite reviews or annotations.
6. **Heavy data stays out of Git.** `data/`, `downloads/`, `repos/`, virtual
   environments and weights stay outside. Card images are not redistributed.
7. **Document in `research/`.** Every block of work leaves a dated document
   with what was done, evidence and pending items. The project's working
   language is Spanish; contributions in English are welcome.

## Flow

1. Fork and create one branch per change.
2. Run the relevant tests with `.venv-eval` and attach the result.
3. Open the pull request explaining what changes, how it was verified and
   what is left out.

For questions, open an issue. There is no chat channel yet.
