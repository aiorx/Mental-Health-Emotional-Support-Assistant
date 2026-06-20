import os
import json
from modelscope.hub.snapshot_download import snapshot_download


def build_emotional_rag_data():
    print("📥 正在绕过解析引擎，直接获取底层 JSON 文件...")

    try:
        # 1. 这一步会瞬间完成，因为它会直接读取你刚才下载好的 907MB 缓存
        dataset_dir = snapshot_download('YIRONGCHEN/SoulChatCorpus', repo_type='dataset')

        # 2. 找到缓存文件夹中的 JSON 数据源
        json_path = os.path.join(dataset_dir, "SoulChatCorpus-sft-multi-Turn.json")
        print(f"✅ 定位到本地数据文件: {json_path}")
        print("⚙️ 正在使用原生 Python 解析数据...")

        # 3. 直接读取，无视所有第三方库的版本冲突
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

    except Exception as e:
        print(f"❌ 读取文件失败: {e}")
        return

    # 我们取前 2000 个多轮对话
    samples = data[:2000]

    output_file = "data/emotional_support.txt"
    os.makedirs("data", exist_ok=True)

    chunks = []

    for sample in samples:
        # 读取里面的对话列表
        messages = sample.get('messages', [])

        # 遍历对话，将 相邻的 来访者(user) -> 咨询师(assistant) 提取为问答对
        for i in range(len(messages) - 1):
            if messages[i].get('role') == 'user' and messages[i + 1].get('role') == 'assistant':
                client_text = messages[i].get('content', '').strip()
                counselor_text = messages[i + 1].get('content', '').strip()

                if client_text and counselor_text:
                    chunk = f"来访者：{client_text}\n咨询师：{counselor_text}"
                    chunks.append(chunk)

    # 写入最终的 txt 文件，用作向量库的输入
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n\n---\n\n".join(chunks))

    print(f"🎉 大功告成！从 {len(samples)} 段原始对话中，提取出 {len(chunks)} 个共情问答对。")
    print(f"📄 已成功写入: {output_file}")
    print("🚀 现在你可以直接运行你的 rag/vector_store.py 了！")


if __name__ == "__main__":
    build_emotional_rag_data()