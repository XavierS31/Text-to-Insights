from datasets import load_dataset
from transformers import AutoProcessor, AutoModelForCausalLM, TrainingArguments, Trainer
from transformers import DataCollatorForLanguageModeling
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
import torch

instruction = """
You are extracting structured data from academic articles on photovoltaic cells.

Instructions:
- Only extract data for the highest efficiency cell reported.
- Match the schema exactly as specified below.
- If any field is not available, return it as "N/A".
- Return a single valid JSON object.
- Do not include markdown or code formatting.
- Skip the article's introduction.
- Only one entry per article is required.

Schema fields:
- research_focus
- key_findings
- device_type
- absorber_material
- absorber_material_term_used
- absorber_dopant_material
- absorber_dopant_material_term_used
- absorber_dopant_polarity
- absorber_dopant_polarity_term_used
- front_surface_morphology
- front_surface_morphology_term_used
- rear_surface_morphology
- rear_surface_morphology_term_used
- front_surface_passivation_material
- front_surface_passivation_material_term_used
- rear_surface_passivation_material
- rear_surface_passivation_material_term_used
- negative_metallization_material
- negative_metallization_material_term_used
- positive_metallization_material
- positive_metallization_material_term_used
- efficiency_percent
- cell_area_cm2
- short_circuit_current_a
- short_circuit_current_density_ma_cm2
- open_circuit_voltage_v
- fill_factor_percent
"""

def format_prompt(example):
    return {
        "text": f"<|start_of_turn|>user\n{instruction}\n\n{example['input']}<|end_of_turn|>\n<|start_of_turn|>model\n{example['output']}<|end_of_turn|>"
    }

dataset = load_dataset("json", data_files="your_data.jsonl", split="train")
dataset = dataset.map(format_prompt)

model_id = "google/gemma-3-4b-it"
processor = AutoProcessor.from_pretrained(model_id)
processor.tokenizer.pad_token = processor.tokenizer.eos_token

def tokenize_function(examples):
    tokens = processor.tokenizer(
        examples["text"],
        truncation=True,
        padding="max_length",
        max_length=2048,
    )
    tokens["labels"] = tokens["input_ids"].copy()
    return tokens

tokenized_dataset = dataset.map(tokenize_function, batched=True, remove_columns=dataset.column_names)

model = AutoModelForCausalLM.from_pretrained(
    model_id,
    load_in_4bit=True,
    torch_dtype=torch.bfloat16,
    device_map="auto",
)

model = prepare_model_for_kbit_training(model)

lora_config = LoraConfig(
    r=16,
    lora_alpha=32,
    target_modules=["q_proj", "v_proj"],
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
)

model = get_peft_model(model, lora_config)

training_args = TrainingArguments(
    output_dir="./gemma3-4b-it-finetuned",
    per_device_train_batch_size=2,
    gradient_accumulation_steps=8,
    warmup_steps=50,
    max_steps=1000,
    learning_rate=2e-5,
    bf16=True,
    logging_dir="./logs",
    logging_steps=20,
    save_steps=200,
    save_total_limit=2,
    evaluation_strategy="no",
    save_strategy="steps",
)

data_collator = DataCollatorForLanguageModeling(processor.tokenizer, mlm=False)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=tokenized_dataset,
    tokenizer=processor.tokenizer,
    data_collator=data_collator,
)

trainer.train()

trainer.save_model("./gemma3-4b-it-finetuned")
