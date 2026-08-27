"""Motor de búsqueda híbrida, ranking explicable y API de Knowledge Nexus.

Este paquete implementa el frente de recuperación: embeddings, búsqueda
vectorial y léxica, expansión de grafo, ranking explicable, ensamblado de
evidencia, generación de oportunidades y la API que consume la interfaz.

La capa de datos canónica (`knowledge_nexus_data`) es de solo lectura: aquí no
se corrigen, regeneran ni reescriben los datos de Data V1.0.
"""

__version__ = "0.1.0"
CONTRACT_VERSION = "1.0"
RANKING_VERSION = "1.0.0"

__all__ = ["__version__", "CONTRACT_VERSION", "RANKING_VERSION"]
