from pathlib import Path
from typing import List

import torch
import typer
import wandb
from rich import print
from transformers import AutoModelForSequenceClassification, AutoTokenizer

# Paths
PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_MODELS_PATH = PROJECT_ROOT / "models"
LOCAL_WANDB_ARTIFACTS_PATH = LOCAL_MODELS_PATH / "wandb_artifacts"
DEFAULT_TRACED_MODEL_PATH = LOCAL_MODELS_PATH / "traced_model.pt"

# Model Constants
DEFAULT_PRETRAINED_MODEL_NAME = "distilbert-base-uncased"
DEFAULT_WANDB_MODEL_REGISTRY__ARTIFACT_NAME = (
    "team_44/model-registry/distilbert-base-uncased-finetuned-news"
)
DEFAULT_WANDB_MODEL_REGISTRY__ARTIFACT_ALIAS = "prod"

NUM_LABELS = 4

app = typer.Typer()

TYPER_ARTIFACT_NAME_HELP = "The name of the W&B model artifact to be used in the format [entity]/[project]/[artifact_name]:[alias]"
TYPER_MODEL_NAME_HELP = "The name of the W&B model in the registry in the format [entity]/[project]/[model_name]"
TYPER_MODEL_ALIAS_HELP = "Alias of the model to be used in the W&B model registry. You can pass this option multiple times to register multiple aliases."


@app.command()
def register_artifact(
    artifact_name: str = typer.Option(
        ...,
        help=TYPER_ARTIFACT_NAME_HELP,
    ),
    model_name: str = typer.Option(
        DEFAULT_WANDB_MODEL_REGISTRY__ARTIFACT_NAME,
        help=TYPER_MODEL_NAME_HELP,
    ),
    model_alias: List[str] = typer.Option(
        [DEFAULT_WANDB_MODEL_REGISTRY__ARTIFACT_ALIAS],
        help=TYPER_MODEL_ALIAS_HELP,
    ),
) -> wandb.Artifact:
    """Registers a WandB artifact from a run in the Model Registry"""
    api = wandb.Api()
    artifact = api.artifact(artifact_name)
    try:
        is_linked = artifact.link(
            target_path=model_name, aliases=[*model_alias]
        )
    except wandb.errors.CommError as comm_error:
        if (
            str(comm_error)
            == "Permission denied, ask the project owner to grant you access"
        ):
            raise ValueError(
                f"Model registry '{model_name}' not found. "
                "Please make sure you have create it using the W&B UI."
            )
    if is_linked:
        print(
            f"[green]Model [bold]'{artifact_name}'[/bold] successfully registered with "
            f"name [bold]'{model_name}'[/bold] with model alias: [bold]'{model_alias}'[/bold][/green]"
        )
        model_registry_url = f"https://wandb.ai/{artifact.entity}/registry/model?selectionPath={model_name}"
        print(f"View at URL: [bold]{model_registry_url}[/bold]")
        return artifact


def convert_model_to_torchscript(model_dir: str) -> torch.jit.ScriptModule:
    """Converts a saved model into TorchScript using tracing."""

    print(f"Loading model from path '{model_dir}'...")
    model = AutoModelForSequenceClassification.from_pretrained(
        model_dir, num_labels=NUM_LABELS, torchscript=True
    )
    # First row in 'ag_news' training dataset
    dummy_input = {
        "text": "Wall St. Bears Claw Back Into the Black (Reuters) Reuters - Short-sellers, Wall Street's dwindling\\band of ultra-cynics, are seeing green again.",
        "label": 2,
    }
    tokenizer = AutoTokenizer.from_pretrained(DEFAULT_PRETRAINED_MODEL_NAME)
    dummy_tokenized_input = tokenizer(
        dummy_input["text"], truncation=True, return_tensors="pt"
    )
    print("Converting model to TorchScript...")
    return torch.jit.trace(model, tuple(dummy_tokenized_input.values()))


@app.command()
def register_and_convert_model(
    artifact_name: str = typer.Option(
        ...,
        help=TYPER_ARTIFACT_NAME_HELP,
    ),
    model_name: str = typer.Option(
        DEFAULT_WANDB_MODEL_REGISTRY__ARTIFACT_NAME,
        help=TYPER_MODEL_NAME_HELP,
    ),
    model_alias: List[str] = typer.Option(
        default=[DEFAULT_WANDB_MODEL_REGISTRY__ARTIFACT_ALIAS],
        help=TYPER_MODEL_ALIAS_HELP,
    ),
):
    """Register a model in the Model Registry, convert it to TorchScript and store it locally."""
    model_artifact = register_artifact(artifact_name, model_name, model_alias)
    model_local_dir = model_artifact.download(root=LOCAL_WANDB_ARTIFACTS_PATH)
    print(f"Saved artifact model to '{LOCAL_WANDB_ARTIFACTS_PATH}'")
    traced_model = convert_model_to_torchscript(model_dir=model_local_dir)
    print(f"Saving traced model in '{DEFAULT_TRACED_MODEL_PATH}'...")
    torch.jit.save(traced_model, DEFAULT_TRACED_MODEL_PATH)
    print("[green]Model successfully registered, converted and saved![/green]")
    return DEFAULT_TRACED_MODEL_PATH


if __name__ == "__main__":
    app()
