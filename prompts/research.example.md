# Research Angle (Example)

> This is a **template example** to show you how to structure your research prompt.
> Replace this content with your own research angle in `research.md`.

## My Research Focus
I am investigating how retrieval-augmented generation (RAG) improves the factual accuracy of large language models in open-domain question answering. Specifically, I want to understand which retrieval strategies (dense, sparse, or hybrid) produce the most reliable context for generation, and how re-ranking affects end-to-end performance.

## My Data
I am building a benchmark pipeline using the BEIR dataset (18 retrieval tasks) and the Natural Questions (NQ) dataset for QA evaluation. My experiments run on a single A100 GPU with a 7B-parameter generator (Llama-2-7b-chat). I evaluate using NDCG@10 for retrieval and exact-match / F1 for QA.

## What I'm Looking For
- Papers comparing dense, sparse, and hybrid retrieval methods on standard benchmarks
- Studies on the impact of re-ranking (cross-encoders, LLM-based rankers) on retrieval quality
- Analyses of how retrieval quality propagates to generation accuracy in RAG systems
- Work on latency/throughput trade-offs in production RAG pipelines
- Novel prompting or fine-tuning strategies that better integrate retrieved context into generation
