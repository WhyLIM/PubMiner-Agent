"""PubEx clients：PubMed / PMC 的受控获取客户端。

约定：
- 网络执行与解析分离：`*_parse` 纯函数可离线 contract test；
- 全部异常走 pubex.errors 的 typed 分类；证书校验失败不重试；
- 只访问本包声明的 NCBI 端点，不发起任何未注册网络请求。
"""
from pubex.clients.pmc import PMCFulltextClient
from pubex.clients.pubmed import AsyncPubMedClient

__all__ = ["AsyncPubMedClient", "PMCFulltextClient"]
