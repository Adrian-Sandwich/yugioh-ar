---
license: apache-2.0
tags:
- image-classification
- generated_from_trainer
datasets:
- imagefolder
metrics:
- accuracy
model-index:
- name: vit-base-blur
  results:
  - task:
      name: Image Classification
      type: image-classification
    dataset:
      name: blurry images
      type: imagefolder
      config: default
      split: train
      args: default
    metrics:
    - name: Accuracy
      type: accuracy
      value: 1.0
---

<!-- This model card has been generated automatically according to the information the Trainer had access to. You
should probably proofread and complete it, then remove this comment. -->

# vit-base-blur

This model is a fine-tuned version of [google/vit-base-patch16-224-in21k](https://huggingface.co/google/vit-base-patch16-224-in21k) on the blurry images dataset.
It achieves the following results on the evaluation set:
- Loss: 0.0008
- Accuracy: 1.0

## Model description

Model trained for binary classification between 'noisy' (blurry) and clean images, where 'noisy' images are the result of unfinished/insufficient passes from an LDM for image generation

## Intended uses & limitations

More information needed

## Training and evaluation data

1000ish clean and blurry images using 30 and 10 steps respectively on SD2.1

## Training procedure

### Training hyperparameters

The following hyperparameters were used during training:
- learning_rate: 0.0001
- train_batch_size: 16
- eval_batch_size: 8
- seed: 42
- optimizer: Adam with betas=(0.9,0.999) and epsilon=1e-08
- lr_scheduler_type: linear
- num_epochs: 12

### Training results

| Training Loss | Epoch | Step | Validation Loss | Accuracy |
|:-------------:|:-----:|:----:|:---------------:|:--------:|
| 0.0082        | 1.02  | 100  | 0.0107          | 1.0      |
| 0.0079        | 2.04  | 200  | 0.0052          | 1.0      |
| 0.0029        | 3.06  | 300  | 0.0028          | 1.0      |
| 0.002         | 4.08  | 400  | 0.0020          | 1.0      |
| 0.0016        | 5.1   | 500  | 0.0015          | 1.0      |
| 0.0013        | 6.12  | 600  | 0.0013          | 1.0      |
| 0.0011        | 7.14  | 700  | 0.0011          | 1.0      |
| 0.001         | 8.16  | 800  | 0.0010          | 1.0      |
| 0.0009        | 9.18  | 900  | 0.0009          | 1.0      |
| 0.0008        | 10.2  | 1000 | 0.0008          | 1.0      |
| 0.0008        | 11.22 | 1100 | 0.0008          | 1.0      |


### Framework versions

- Transformers 4.30.2
- Pytorch 2.0.1+cu118
- Datasets 2.13.1
- Tokenizers 0.13.3
