import os
import pandas as pd
from huggingface_hub import snapshot_download


def build_psychology_books_data():
    print("📥 正在通过国内镜像直连 HuggingFace...")
    # 🌟 核心魔法：强制使用国内镜像节点，解决 100% 的网络墙问题
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

    try:
        # 1. 直接下载仓库文件到本地缓存（瞬间完成或极快）
        dataset_dir = snapshot_download(repo_id="Mxode/Chinese-Psychology-Books", repo_type="dataset")
        print(f"✅ 成功定位到本地缓存目录: {dataset_dir}")

        # 2. 自动寻找数据文件（可能是 .csv 或者是 HF 自动转换的 .parquet）
        data_file = None

        # 优先找根目录下的 csv
        for f in os.listdir(dataset_dir):
            if f.endswith('.csv'):
                data_file = os.path.join(dataset_dir, f)
                break

        # 如果根目录没有，去 data/ 目录下找 parquet
        if not data_file:
            data_dir = os.path.join(dataset_dir, "data")
            if os.path.exists(data_dir):
                for f in os.listdir(data_dir):
                    if f.endswith('.parquet'):
                        data_file = os.path.join(data_dir, f)
                        break

        if not data_file:
            print("❌ 未能找到有效的 .csv 或 .parquet 文件。")
            return

        print(f"📄 找到底层数据文件: {os.path.basename(data_file)}")
        print("⚙️ 正在解析数据...")

        # 3. 使用 pandas 读取表格数据
        if data_file.endswith('.csv'):
            df = pd.read_csv(data_file)
        else:
            df = pd.read_parquet(data_file)

        # 4. 自动探测包含文本的列名（比如 'text', 'content' 等）
        text_col = None
        for col in ['text', 'content', 'passage', 'sentence']:
            if col in df.columns:
                text_col = col
                break

        # 如果没按套路出牌，就硬核抓取第一列包含字符串的列
        if not text_col:
            for col in df.columns:
                if df[col].dtype == 'object':
                    text_col = col
                    break

        if not text_col:
            print("❌ 无法在表格中识别到文字列！")
            return

        print(f"🔍 锁定知识文本列：`{text_col}`，开始提取...")

        chunks = []
        # 5. 遍历并清洗数据
        for item in df[text_col].dropna():
            text = str(item).strip()
            # 过滤掉过短的无意义字符
            if len(text) > 15:
                chunks.append(text)

        output_file = "data/psychology_books.txt"
        os.makedirs("data", exist_ok=True)

        # 6. 使用你的 RAG 分隔符写入文件
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("\n\n---\n\n".join(chunks))

        print(f"🎉 大功告成！成功提取 {len(chunks)} 条纯正的心理学通识知识！")
        print(f"📁 数据已写入: {output_file}")
        print("🚀 现在，你可以继续运行 vector_store.py 把它们灌入向量库了！")

    except ImportError:
        print("❌ 缺少必要的解析库，请在终端运行：")
        print("   pip install huggingface_hub pandas pyarrow")
    except Exception as e:
        print(f"❌ 运行发生错误: {e}")


if __name__ == "__main__":
    build_psychology_books_data()