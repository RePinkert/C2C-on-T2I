# 统计汇总（配对 Wilcoxon + bootstrap 95% CI）

| matrix | metric | 对比 | n | mean A | mean B | diff | 95% CI | p | rank-biserial |
|---|---|---|---|---|---|---|---|---|---|
| qwen3_0.6b+qwen2.5_0.5b@krea2 | clip_user | raw vs t2t | 24 | 0.245 | 0.236 | 0.009 | [-0.0006, 0.0181] | 0.14904 | 0.6683 |
| qwen3_0.6b+qwen2.5_0.5b@krea2 | clip_user | raw vs c2c | 24 | 0.245 | 0.2453 | -0.0003 | [-0.0055, 0.0053] | 0.704756 | 0.5467 |
| qwen3_0.6b+qwen2.5_0.5b@krea2 | clip_user | t2t vs c2c | 24 | 0.236 | 0.2453 | -0.0093 | [-0.0181, -0.0009] | 0.056427 | 0.7233 |
| qwen3_0.6b+qwen2.5_0.5b@krea2 | clip_enhanced | raw vs t2t | 24 | 0.245 | 0.2504 | -0.0054 | [-0.0151, 0.0036] | 0.423687 | 0.5933 |
| qwen3_0.6b+qwen2.5_0.5b@krea2 | clip_enhanced | raw vs c2c | 24 | 0.245 | 0.2551 | -0.0101 | [-0.0209, -0.0008] | 0.187501 | 0.6567 |
| qwen3_0.6b+qwen2.5_0.5b@krea2 | clip_enhanced | t2t vs c2c | 24 | 0.2504 | 0.2551 | -0.0047 | [-0.0127, 0.0043] | 0.119418 | 0.6817 |
| qwen3_0.6b+qwen2.5_0.5b@krea2 | aesthetic | raw vs t2t | 24 | 6.3735 | 6.2357 | 0.1378 | [-0.0004, 0.2721] | 0.064649 | 0.7167 |
| qwen3_0.6b+qwen2.5_0.5b@krea2 | aesthetic | raw vs c2c | 24 | 6.3735 | 6.3817 | -0.0083 | [-0.1518, 0.1327] | 1.0 | 0.5 |
| qwen3_0.6b+qwen2.5_0.5b@krea2 | aesthetic | t2t vs c2c | 24 | 6.2357 | 6.3817 | -0.1461 | [-0.296, 0.017] | 0.095096 | 0.6967 |
| qwen3_0.6b+qwen2.5_0.5b@moss | clip_user | raw vs t2t | 84 | 0.2203 | 0.215 | 0.0053 | [-0.0018, 0.0127] | 0.275875 | 0.579 |
| qwen3_0.6b+qwen2.5_0.5b@moss | clip_user | raw vs c2c | 84 | 0.2203 | 0.2061 | 0.0142 | [0.0034, 0.0273] | 0.054025 | 0.621 |
| qwen3_0.6b+qwen2.5_0.5b@moss | clip_user | t2t vs c2c | 84 | 0.215 | 0.2061 | 0.0089 | [-0.0, 0.0183] | 0.058326 | 0.6286 |
| qwen3_0.6b+qwen2.5_0.5b@moss | clip_enhanced | raw vs t2t | 84 | 0.2203 | 0.2685 | **-0.0482** | [-0.061, -0.0359] | **0.0** | 0.8584 |
| qwen3_0.6b+qwen2.5_0.5b@moss | clip_enhanced | raw vs c2c | 84 | 0.2203 | 0.2587 | **-0.0384** | [-0.0542, -0.0227] | **3.3e-05** | 0.7609 |
| qwen3_0.6b+qwen2.5_0.5b@moss | clip_enhanced | t2t vs c2c | 84 | 0.2685 | 0.2587 | 0.0098 | [0.0016, 0.0186] | 0.242618 | 0.5734 |
| qwen3_0.6b+qwen2.5_0.5b@moss | aesthetic | raw vs t2t | 84 | 6.4174 | 6.2882 | 0.1291 | [0.0002, 0.2636] | 0.117493 | 0.5983 |
| qwen3_0.6b+qwen2.5_0.5b@moss | aesthetic | raw vs c2c | 84 | 6.4174 | 6.3328 | 0.0846 | [-0.0448, 0.2164] | 0.228536 | 0.5756 |
| qwen3_0.6b+qwen2.5_0.5b@moss | aesthetic | t2t vs c2c | 84 | 6.2882 | 6.3328 | -0.0446 | [-0.1822, 0.0783] | 0.59253 | 0.5336 |
| qwen3_0.6b+qwen3_4b_base@moss | clip_user | raw vs t2t | 24 | 0.2536 | 0.2429 | 0.0107 | [0.001, 0.0217] | 0.107383 | 0.69 |
| qwen3_0.6b+qwen3_4b_base@moss | clip_user | raw vs c2c | 24 | 0.2536 | 0.2533 | 0.0003 | [-0.0073, 0.009] | 0.564589 | 0.57 |
| qwen3_0.6b+qwen3_4b_base@moss | clip_user | t2t vs c2c | 24 | 0.2429 | 0.2533 | -0.0104 | [-0.0202, -0.0011] | 0.052641 | 0.7267 |
| qwen3_0.6b+qwen3_4b_base@moss | clip_enhanced | raw vs t2t | 24 | 0.2536 | 0.2647 | -0.0111 | [-0.0312, 0.0072] | 0.490799 | 0.5833 |
| qwen3_0.6b+qwen3_4b_base@moss | clip_enhanced | raw vs c2c | 24 | 0.2536 | 0.2761 | **-0.0225** | [-0.0411, -0.0058] | **0.026928** | 0.7567 |
| qwen3_0.6b+qwen3_4b_base@moss | clip_enhanced | t2t vs c2c | 24 | 0.2647 | 0.2761 | **-0.0114** | [-0.022, -0.0009] | **0.033985** | 0.7467 |
| qwen3_0.6b+qwen3_4b_base@moss | aesthetic | raw vs t2t | 24 | 6.3886 | 6.1724 | 0.2162 | [0.0127, 0.443] | 0.207617 | 0.65 |
| qwen3_0.6b+qwen3_4b_base@moss | aesthetic | raw vs c2c | 24 | 6.3886 | 6.4473 | -0.0587 | [-0.3069, 0.1705] | 0.855336 | 0.5233 |
| qwen3_0.6b+qwen3_4b_base@moss | aesthetic | t2t vs c2c | 24 | 6.1724 | 6.4473 | -0.2749 | [-0.5493, -0.0368] | 0.151501 | 0.67 |
