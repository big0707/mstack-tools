# 管理身份与 Chrome 使用边界

这里只保存**用途和隔离规则**。把占位符换成你们自己的账号，不要把真实密钥写入本仓库。

## 1. 产品权限管理员

- 用途：仅在 Service Account 或公开 API 无法完成时，处理授权、加人、减人、改权。
- 建议使用一个专用 Chrome profile，并先核对页面可见邮箱。
- 不要用这个身份读分析报表、投放广告、改预算、发布内容、改 GTM 标签或管理 GCP Service Account。
- 连错 profile、未登录或看不到目标资源时停止，不要换号或扩大范围。

## 2. GCP Service Account 生命周期

- 与产品权限管理员分开。
- 创建、停用或删除 SA 前先说明对 GA / GTM / Ads / GSC 作业的影响。
- 员工离职不等于删除共享 Service Account。
- 创建 SA 不默认附带下载私钥或项目 Owner/Editor。

## 3. API 身份隔离

- GMP 管人：`YOUR_GMP_SA@YOUR_GCP_PROJECT.iam.gserviceaccount.com`
- Ads 投放：`YOUR_ADS_SA@YOUR_GCP_PROJECT.iam.gserviceaccount.com`
- GSC 查询：`YOUR_GSC_SA@YOUR_GCP_PROJECT.iam.gserviceaccount.com`

缺少密钥或邮箱不匹配时必须失败退出，禁止回退到投放身份。
