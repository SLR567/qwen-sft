from datasets import Dataset
import pandas as pd
from transformers import AutoTokenizer, AutoModelForCausalLM, DataCollatorForSeq2Seq, TrainingArguments, Trainer, GenerationConfig

df = pd.read_json('/home/yc37974/lrs/marketing_data_generation_digitaling/marketing_text.json')
ds = Dataset.from_pandas(df)

tokenizer = AutoTokenizer.from_pretrained('/data/jianbingshen/module/Qwen2-7B-Instruct', use_fast=False, trust_remote_code=True)

def process_func(example):
    #MAX_LENGTH = 384    # Llama分词器会将一个中文字切分为多个token，因此需要放开一些最大长度，保证数据的完整性
    MAX_LENGTH = 2500
    input_ids, attention_mask, labels = [], [], []
    #instruction = tokenizer(f"<|im_start|>system\n现在你要扮演皇帝身边的女人--甄嬛<|im_end|>\n<|im_start|>user\n{example['instruction'] + example['input']}<|im_end|>\n<|im_start|>assistant\n", add_special_tokens=False)  # add_special_tokens 不在开头加 special_tokens
    instruction = tokenizer(f"<|im_start|>system\n现在你要扮演一个撰写营销软文的网络写手<|im_end|>\n<|im_start|>user\n{example['instruction'] + example['input']}<|im_end|>\n<|im_start|>assistant\n", add_special_tokens=False)  # add_special_tokens 不在开头加 special_tokens
    response = tokenizer(f"{example['output']}", add_special_tokens=False)
    input_ids = instruction["input_ids"] + response["input_ids"] + [tokenizer.pad_token_id]
    attention_mask = instruction["attention_mask"] + response["attention_mask"] + [1]  # 因为eos token咱们也是要关注的所以 补充为1
    labels = [-100] * len(instruction["input_ids"]) + response["input_ids"] + [tokenizer.pad_token_id]  
    if len(input_ids) > MAX_LENGTH:  # 做一个截断
        input_ids = input_ids[:MAX_LENGTH]
        attention_mask = attention_mask[:MAX_LENGTH]
        labels = labels[:MAX_LENGTH]
    return {
        "input_ids": input_ids,
        "attention_mask": attention_mask,
        "labels": labels
    }


tokenized_id = ds.map(process_func, remove_columns=ds.column_names)

import torch

model = AutoModelForCausalLM.from_pretrained('/data/jianbingshen/module/Qwen2-7B-Instruct', device_map="auto",torch_dtype=torch.bfloat16)

model.enable_input_require_grads() # 开启梯度检查点时，要执行该方法

from peft import LoraConfig, TaskType, get_peft_model

config = LoraConfig(
    task_type=TaskType.CAUSAL_LM, 
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    inference_mode=False, # 训练模式
    r=8, # Lora 秩
    lora_alpha=32, # Lora alaph，具体作用参见 Lora 原理
    lora_dropout=0.1# Dropout 比例
)

model = get_peft_model(model, config)
model=model.to('cuda')

args = TrainingArguments(
    output_dir="/data/jianbingshen/module/Qwen2_7B_instruct_lora",
    per_device_train_batch_size=4,
    gradient_accumulation_steps=4,
    logging_steps=10,
    num_train_epochs=3,
    save_steps=10, # 为了快速演示，这里设置10，建议你设置成100
    learning_rate=1e-4,
    save_on_each_node=True,
    gradient_checkpointing=True
)

trainer = Trainer(
    model=model,
    args=args,
    train_dataset=tokenized_id,
    data_collator=DataCollatorForSeq2Seq(tokenizer=tokenizer, padding=True),
)
trainer.train()

trainer.save_model()

from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
from peft import PeftModel

mode_path = '/data/jianbingshen/module/Qwen2-7B-Instruct/'
#lora_path = '/data/jianbingshen/module/Qwen2_7B_instruct_lora/checkpoint-10' # 这里改称你的 lora 输出对应 checkpoint 地址
lora_path = '/data/jianbingshen/module/Qwen2_7B_instruct_lora' # 这里改成你的 lora 输出对应 checkpoint 地址

# 加载tokenizer
tokenizer = AutoTokenizer.from_pretrained(mode_path, trust_remote_code=True)

# 加载模型
model = AutoModelForCausalLM.from_pretrained(mode_path, device_map="auto",torch_dtype=torch.bfloat16, trust_remote_code=True).eval()

# 加载lora权重
model = PeftModel.from_pretrained(model, model_id=lora_path)
model=model.to('cuda')

prompt = "请撰写软文，标题为：2024年内容运营必备的5个提案技巧"
#prompt = "请撰写软文，标题为：碎屏时代，品牌营销的新五感"
messages = [
    {"role": "system", "content": "现在你要扮演一个撰写营销软文的网络写手"},
    #{"role": "user", "content": "假设你是皇帝身边的女人--甄嬛。"},
    {"role": "user", "content": prompt}
]
inputs = tokenizer.apply_chat_template(messages,add_generation_prompt=True,tokenize=True,return_tensors="pt",return_dict=True).to('cuda')
#inputs = tokenizer.apply_chat_template(messages,add_generation_prompt=True,tokenize=True,return_tensors="pt",return_dict=True)


gen_kwargs = {"max_length": 2500, "do_sample": True, "top_k": 1}
with torch.no_grad():
    outputs = model.generate(**inputs, **gen_kwargs)
    outputs = outputs[:, inputs['input_ids'].shape[1]:]
    print(tokenizer.decode(outputs[0], skip_special_tokens=True))









