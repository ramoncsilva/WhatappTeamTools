# Constituição do Projeto

Princípios que valem para **toda** spec, plano e código deste repositório. Se uma spec contradiz
um princípio, ou a spec muda, ou o princípio é emendado aqui primeiro (com justificativa).

| # | Princípio | Consequência prática |
|---|-----------|----------------------|
| C-1 | **Enxuto primeiro** | Uma única Lambda, sem dependências de terceiros (apenas stdlib + `boto3` já presente no runtime), sem camadas, VPC, contêiner ou framework. |
| C-2 | **Free tier "Always Free" sempre** | Só entram serviços AWS cujo free tier **não expira** em 12 meses (Lambda, DynamoDB provisionado, EventBridge Scheduler, SSM Parameter Store standard, SNS, CloudWatch Logs, CloudFormation, IAM). Proibido: S3, EFS, RDS, Secrets Manager, NAT/VPC endpoints, DynamoDB on-demand, PITR, KMS com chave própria. |
| C-3 | **Segredo nunca no repositório** | Credenciais vivem em `config/app.properties` (local, no `.gitignore`) e são enviadas pelo script de deploy para SSM SecureString. Nunca em template, variável de ambiente, log ou commit. |
| C-4 | **Spec é a fonte da verdade** | Mudança de comportamento começa na spec. Cada requisito tem ID (`FR-xx`, `NFR-xx`) rastreável até um critério de aceite (`AC-xx`) e uma tarefa (`T-xx`). |
| C-5 | **Sorteio atômico, auditável e idempotente** | Um sorteio é o conjunto completo *tarefa → pessoa*, gravado tudo-ou-nada, com semente, probabilidades e justificativas. No máximo um sorteio por (time, semana ISO). |
| C-6 | **Transparência para o time** | Toda mensagem mostra a probabilidade de cada escolha e explica qualquer exceção às premissas. |
| C-7 | **Dados pessoais mínimos** | Só nome e identificadores; o roster real fica fora do git; logs usam IDs, não nomes. |
| C-8 | **Núcleo puro, bordas finas** | O algoritmo (árvore de soma, solver, sorteio, mensagem) é função pura e testável sem rede nem AWS; DynamoDB e HTTP ficam em módulos de borda. |
