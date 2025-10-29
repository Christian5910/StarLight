"""
Assistente Educacional Starlight - Aplicação Principal

Este script implementa um assistente de voz para fins educacionais, operado por teclado ou botões, à depender da versão.
Ele utiliza reconhecimento de voz para capturar perguntas, um motor de busca local
baseado em arquivos JSON para encontrar respostas, e text-to-speech (TTS) para
interagir com o usuário.

A navegação é feita através do console com uma interface de texto simples.
"""

import json
import speech_recognition as sr
import os
import random
import time
import platform
import subprocess
import re
import unicodedata
from pathlib import Path

# =========================
# CONFIGURAÇÕES GLOBAIS
# =========================
class Config:
    """Configurações globais do sistema"""
    
    # Diretório contendo os arquivos JSON organizados por tema/subtema
    PASTA_JSONS = "Jsons"
    
    # Modelo de reconhecimento de voz offline (fallback se pyttsx3 falhar)
    PASTA_MODELO_VOSK = "vosk-model-small-pt-0.3"
    
    # Idioma para reconhecimento de voz (pt-BR para melhor acurácia com sotaque brasileiro)
    IDIOMA_RECONHECIMENTO = 'pt-BR'
    
    # Controla exibição das instruções iniciais (apenas primeira execução)
    PRIMEIRA_EXECUCAO = True
    
    
# =========================
# TTS COM BLOQUEIO OTIMIZADO
# =========================
class GerenciadorTTS:
    def __init__(self):
        print("🔊 Iniciando TTS...")
        self.voice_id = self._encontrar_voz_pt()
        self.falando = False
        self.ultima_fala_time = 0
        print("✅ TTS Carregado!")
    
    def _encontrar_voz_pt(self):
        """Encontra a melhor voz em português"""
        try:
            import pyttsx3
            engine = pyttsx3.init()
            voices = engine.getProperty('voices')
            
            for voice in voices:
                if any(term in voice.name.lower() for term in ['português', 'brazil', 'portuguese', 'pt-br']):
                    print(f"✅ Voz: {voice.name}")
                    engine.stop()
                    return voice.id
            
            if voices:
                print(f"⚠️  Voz padrão: {voices[0].name}")
                engine.stop()
                return voices[0].id
                
            return None
            
        except Exception as e:
            print(f"❌ Erro ao buscar vozes: {e}")
            return None
    
    def falar(self, texto):
        """Sintetiza fala do texto com sistema de bloqueio para evitar sobreposição"""
        # Ignora textos vazios para evitar chamadas desnecessárias ao TTS
        if not texto or not texto.strip():
            return
            
        print(f"🎤 IA: {texto}")
        self.falando = True
        
        try:
            import pyttsx3
            engine = pyttsx3.init()
            
            engine.setProperty('rate', 170)
            engine.setProperty('volume', 1.0)
            
            if self.voice_id:
                engine.setProperty('voice', self.voice_id)
            
            engine.say(texto)
            engine.runAndWait()
            engine.stop()
            
        except RuntimeError as e:
            # A biblioteca pyttsx3 pode lançar este erro se uma nova fala for solicitada
            # antes que o loop de execução anterior tenha sido completamente finalizado.
            # Chamamos um método alternativo para garantir que a fala não seja perdida.
            if "run loop already started" in str(e):
                self._falar_alternativo(texto)
            else:
                print(f"❌ Erro Runtime: {e}")
        except Exception as e:
            print(f"❌ Erro ao falar: {e}")
        finally:
            self.falando = False
            self.ultima_fala_time = time.time()
    
    def pode_processar_tecla(self):
        """
        Verifica se o sistema pode processar nova entrada de tecla.
        
        Implementa duplo bloqueio para evitar:
        - Processamento durante fala (flag 'falando')
        - Processamento imediatamente após fala (debounce de 300ms)
        
        Returns:
            bool: True se pode processar tecla, False caso contrário
        """
        # Bloqueia durante síntese de fala ativa
        if self.falando:
            return False
        
        # Debounce: evita processar teclas muito rápido após terminar de falar
        if time.time() - self.ultima_fala_time < 0.3:
            return False
            
        return True
    
    def _falar_alternativo(self, texto):
        """Método alternativo"""
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty('rate', 170)
            engine.say(texto)
            engine.runAndWait()
            engine.stop()
        except:
            print(f"🔊 [FALLBACK]: {texto}")

# =========================
# MOTOR DE BUSCA INTELIGENTE MELHORADO
# =========================
class MotorBusca:
    """
    Sistema de busca inteligente para perguntas educacionais.
    
    Responsável por carregar a base de conhecimento, processar perguntas
    do usuário e encontrar as respostas mais relevantes usando um sistema
    de pontuação baseado em palavras-chave e similaridade textual.
    
    Attributes:
        pasta_base (Path): Caminho para os arquivos JSON de conhecimento
        estrutura_temas (dict): Mapeamento de temas e subtemas carregados
        stop_words (set): Conjunto de palavras irrelevantes para busca
    """
    def __init__(self, pasta_base: str):
        self.pasta_base = Path(pasta_base)
        self.conversor = ConversorNumeros()
        self.estrutura_temas = self._carregar_estrutura_temas()
        
        self.stop_words = {
            'a', 'o', 'as', 'os', 'um', 'uma', 'uns', 'umas', 'de', 'do', 'da', 'dos', 'das',
            'em', 'no', 'na', 'nos', 'nas', 'por', 'para', 'com', 'sem', 'sob', 'sobre',
            'que', 'qual', 'quem', 'cujo', 'onde', 'como', 'quando', 'e', 'ou', 'mas', 'se',
            'me', 'te', 'lhe', 'nos', 'vos', 'lhes', 'eu', 'tu', 'ele', 'ela', 'nós', 'vós',
            'eles', 'elas', 'é', 'são', 'foi', 'era', 'fale', 'sobre', 'diga', 'explique',
            'oque', 'qualé', 'quemé', 'comoé'  # ✅ Palavras comuns em perguntas
        }

    def _carregar_estrutura_temas(self):
        estrutura = {}
        if not self.pasta_base.exists():
            print(f"❌ Pasta {self.pasta_base} não encontrada!")
            return estrutura
            
        for tema_path in self.pasta_base.iterdir():
            if tema_path.is_dir():
                tema_nome = tema_path.name
                subtemas = [f.stem for f in tema_path.glob("*.json")]
                if subtemas:
                    estrutura[tema_nome] = subtemas
        
        print(f"✅ Estrutura carregada: {len(estrutura)} temas")
        return estrutura

    def carregar_json(self, tema: str, subtema: str):
        """Carrega JSON com expansão de palavras-chave"""
        try:
            caminho = self.pasta_base / tema / f"{subtema}.json"
            with open(caminho, 'r', encoding='utf-8') as f:
                dados = json.load(f)
            
            for item in dados:
                if "palavras_chave" in item:
                    item["palavras_chave"] = self.conversor.expandir_palavras_chave_com_numeros(
                        item["palavras_chave"]
                    )
            
            return dados
        except Exception as e:
            print(f"❌ Erro ao carregar {tema}/{subtema}.json: {e}")
            return []

    def _extrair_palavras_chave(self, texto):
        if not texto:
            return set(), ""
        
        texto_limpo = self.normalizar_texto(texto)
        palavras = set(texto_limpo.split())
        palavras_relevantes = palavras - self.stop_words
        
        print(f"🔍 Palavras-chave: {list(palavras_relevantes)}")
        return palavras_relevantes, texto_limpo

    def _calcular_pontuacao(self, palavras_usuario, palavras_chave_item, texto_usuario_normalizado):
        """
        Calcula pontuação de relevância entre pergunta do usuário e item da base.
        
        Usa múltiplas estratégias:
        - Contagem de palavras-chave comuns
        - Bônus por frases similares (permite 1 palavra diferente)
        - Bônus por ordem correta das palavras
        
        Args:
            palavras_usuario: Palavras-chave da pergunta do usuário
            palavras_chave_item: Palavras-chave do item da base
            texto_usuario_normalizado: Texto da pergunta normalizado
        
        Returns:
            int: Pontuação total de relevância
        """
        pontuacao_palavras = len(palavras_usuario.intersection(palavras_chave_item))
        
        bonus_frase = 0
        for palavra_chave in palavras_chave_item:
            if len(palavra_chave.split()) > 1:
                # MELHORIA: Busca por partes da frase também
                palavras_frase = palavra_chave.split()
                palavras_encontradas = sum(1 for palavra in palavras_frase if palavra in texto_usuario_normalizado)
                
                # A correspondência de frase é flexível, permitindo que uma palavra esteja
                # ausente. Isso ajuda a capturar a intenção mesmo com pequenos erros de
                # reconhecimento de voz ou o uso de palavras de ligação diferentes (ex: "o que é" vs "o que foi").
                if palavras_encontradas >= len(palavras_frase) - 1:  # Permite 1 palavra diferente
                    bonus_frase += 3
                    print(f"🎯 Frase similar: '{palavra_chave}'")
        
        # ✅ MELHORIA: Bônus para ordem das palavras
        bonus_ordem = 0
        for palavra_chave in palavras_chave_item:
            if palavra_chave in texto_usuario_normalizado:
                # Verifica se as palavras estão na mesma ordem
                palavras_chave_ordem = palavra_chave.split()
                if len(palavras_chave_ordem) > 1:
                    texto_palavras = texto_usuario_normalizado.split()
                    for i in range(len(texto_palavras) - len(palavras_chave_ordem) + 1):
                        if texto_palavras[i:i+len(palavras_chave_ordem)] == palavras_chave_ordem:
                            # O bônus por ordem correta é menor que o de frase, mas ainda significativo.
                            bonus_ordem += 2
                            print(f"🔤 Ordem correta: '{palavra_chave}'")
                            break
        
        return pontuacao_palavras + bonus_frase + bonus_ordem

    def buscar_resposta_inteligente(self, pergunta_usuario, tema_atual=None, subtema_atual=None):
        """
        Encontra a resposta mais relevante usando busca hierárquica.
        
        A busca é realizada em 3 níveis:
        1. Subtema atual (prioridade máxima)
        2. Tema atual (se não encontrou no subtema)
        3. Base completa (fallback)
        
        Args:
            pergunta_usuario (str): Pergunta digitada ou falada pelo usuário
            tema_atual (str, optional): Tema atual para limitar busca inicial
            subtema_atual (str, optional): Subtema atual para busca prioritária
        
        Returns:
            tuple: (resposta_encontrada, item_completo, pontuacao) 
                ou (None, None, 0) se não encontrar
        """
        
        print(f"🔍 Buscando: '{pergunta_usuario}'")
        # ...
        print(f"🔍 Buscando: '{pergunta_usuario}'")
        
        palavras_usuario, texto_normalizado = self._extrair_palavras_chave(pergunta_usuario)
        
        if not palavras_usuario:
            return None, None, 0
        
        melhor_resposta = None
        melhor_item = None
        maior_pontuacao = 0
        
        if tema_atual and subtema_atual:
            dados_subtema = self.carregar_json(tema_atual, subtema_atual)
            if dados_subtema:
                melhor_resposta, melhor_item, maior_pontuacao = self._buscar_em_dados(
                    palavras_usuario, texto_normalizado, dados_subtema, melhor_resposta, melhor_item, maior_pontuacao
                )
                
        # Se a pontuação ainda for baixa dentro do subtema atual, expande a busca
        # para outros subtemas dentro do mesmo tema. O limiar de 3 foi escolhido
        # para evitar buscas desnecessárias se uma boa correspondência já foi encontrada.
        
        if tema_atual and (maior_pontuacao < 3):  #REDUZIDO: Busca mais cedo em outros subtemas
            subtemas = self.estrutura_temas.get(tema_atual, [])
            for subtema in subtemas:
                if subtema == subtema_atual:
                    continue
                    
                dados_outro_subtema = self.carregar_json(tema_atual, subtema)
                if dados_outro_subtema:
                    resposta_temp, item_temp, pontuacao_temp = self._buscar_em_dados(
                        palavras_usuario, texto_normalizado, dados_outro_subtema, melhor_resposta, melhor_item, maior_pontuacao
                    )
                    
                    if pontuacao_temp > maior_pontuacao:
                        melhor_resposta, melhor_item, maior_pontuacao = resposta_temp, item_temp, pontuacao_temp
        
        if maior_pontuacao > 0:
            print(f"🎯 Encontrado (pontuação: {maior_pontuacao})")
            return melhor_resposta, melhor_item, maior_pontuacao
        else:
            return None, None, 0

    def _buscar_em_dados(self, palavras_usuario, texto_normalizado, dados, melhor_resposta, melhor_item, maior_pontuacao):
        for item in dados:
            palavras_chave_item = set()
            frases_chave_item = []
            
            for palavra_chave in item.get("palavras_chave", []):
                palavras_normalizadas = self._extrair_palavras_chave(palavra_chave)[0]
                palavras_chave_item.update(palavras_normalizadas)
                
                if ' ' in palavra_chave:
                    frase_normalizada = self.normalizar_texto(palavra_chave)
                    frases_chave_item.append(frase_normalizada)
            
            palavras_chave_com_frases = palavras_chave_item.copy()
            for frase in frases_chave_item:
                palavras_chave_com_frases.update(frase.split())
            
            pontuacao = self._calcular_pontuacao(palavras_usuario, palavras_chave_com_frases, texto_normalizado)
            
            # ✅ MELHORIA: Bônus maior para similaridade na pergunta
            pergunta_item_normalizada = self.normalizar_texto(item.get('pergunta', ''))
            if texto_normalizado in pergunta_item_normalizada:
                pontuacao += 3
            elif any(palavra in pergunta_item_normalizada for palavra in palavras_usuario if len(palavra) > 3):
                pontuacao += 1
            
            if pontuacao > maior_pontuacao:
                maior_pontuacao = pontuacao
                melhor_resposta = item['resposta']
                melhor_item = item
        
        return melhor_resposta, melhor_item, maior_pontuacao

    def obter_sugestoes_perguntas(self, tema_atual, quantidade=2):
        """✅ MELHORIA: Retorna múltiplas sugestões de perguntas"""
        sugestoes = []
        
        # Primeiro tenta no tema atual
        if tema_atual:
            subtemas = self.estrutura_temas.get(tema_atual, [])
            for subtema in random.sample(subtemas, min(3, len(subtemas))):
                dados = self.carregar_json(tema_atual, subtema)
                if dados and len(dados) > 0:
                    itens_aleatorios = random.sample(dados, min(quantidade, len(dados)))
                    for item in itens_aleatorios:
                        sugestoes.append({
                            'pergunta': item['pergunta'],
                            'tema': tema_atual,
                            'subtema': subtema
                        })
                    if len(sugestoes) >= quantidade:
                        return sugestoes[:quantidade]
        
        # Se não encontrou o suficiente, busca em outros temas
        outros_temas = [tema for tema in self.estrutura_temas.keys() if tema != tema_atual]
        for tema in random.sample(outros_temas, min(2, len(outros_temas))):
            subtemas = self.estrutura_temas.get(tema, [])
            for subtema in random.sample(subtemas, min(2, len(subtemas))):
                dados = self.carregar_json(tema, subtema)
                if dados and len(dados) > 0:
                    itens_aleatorios = random.sample(dados, min(quantidade - len(sugestoes), len(dados)))
                    for item in itens_aleatorios:
                        sugestoes.append({
                            'pergunta': item['pergunta'],
                            'tema': tema,
                            'subtema': subtema
                        })
                    if len(sugestoes) >= quantidade:
                        return sugestoes[:quantidade]
        
        return sugestoes

    def obter_item_aleatorio_tema(self, tema):
        """Retorna o ITEM completo de um tema"""
        subtemas = self.estrutura_temas.get(tema, [])
        if not subtemas:
            return None, None
            
        for _ in range(5):
            subtema = random.choice(subtemas)
            dados = self.carregar_json(tema, subtema)
            if dados and len(dados) > 0:
                item = random.choice(dados)
                return item, subtema
                
        return None, None

    def obter_item_aleatorio_geral(self):
        """Retorna o ITEM completo de qualquer tema"""
        temas = list(self.estrutura_temas.keys())
        if not temas:
            return None, None, None
            
        for _ in range(10):
            tema = random.choice(temas)
            subtemas = self.estrutura_temas.get(tema, [])
            if subtemas:
                subtema = random.choice(subtemas)
                dados = self.carregar_json(tema, subtema)
                if dados and len(dados) > 0:
                    item = random.choice(dados)
                    return item, tema, subtema
                    
        return None, None, None

    def remover_acentos(self, texto):
        if not texto:
            return ""
        texto = unicodedata.normalize('NFKD', texto)
        return ''.join(c for c in texto if not unicodedata.combining(c))

    def normalizar_texto(self, texto):
        if not texto:
            return ""
        texto = texto.lower().strip()
        texto = self.remover_acentos(texto)
        texto = re.sub(r'[^\w\s]', '', texto)
        return ' '.join(texto.split())

# =========================
# CONVERSOR DE NÚMEROS
# =========================
class ConversorNumeros:
    @staticmethod
    def numero_para_texto(numero_str: str) -> str:
        try:
            dig = numero_str.replace(',', '').replace('.', '')
            if not dig.isdigit():
                return numero_str
            numero = int(dig)
            if numero <= 100:
                return ConversorNumeros._converter_pequeno(numero)
            else:
                return ' '.join(ConversorNumeros._converter_digitos(ch) for ch in dig if ch.isdigit())
        except Exception:
            return numero_str

    @staticmethod
    def _converter_pequeno(numero: int) -> str:
        unidades = ["zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove"]
        especiais = ["dez", "onze", "doze", "treze", "quatorze", "quinze", "dezesseis", "dezessete", "dezoito", "dezenove"]
        dezenas = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa"]

        if numero <= 9:
            return unidades[numero]
        elif 10 <= numero <= 19:
            return especiais[numero - 10]
        elif numero == 100:
            return "cem"
        else:
            dez = numero // 10
            unid = numero % 10
            if unid == 0:
                return dezenas[dez]
            else:
                return dezenas[dez] + " e " + unidades[unid]

    @staticmethod
    def _converter_digitos(digito: str) -> str:
        digitos = {
            '0': 'zero', '1': 'um', '2': 'dois', '3': 'três', '4': 'quatro',
            '5': 'cinco', '6': 'seis', '7': 'sete', '8': 'oito', '9': 'nove'
        }
        return digitos.get(digito, digito)

    @staticmethod
    def expandir_palavras_chave_com_numeros(palavras_chave: list) -> list:
        novas = []
        for palavra in palavras_chave:
            if palavra is None:
                continue
            p = str(palavra).strip()
            if p.replace(',', '').replace('.', '').isdigit():
                t = ConversorNumeros.numero_para_texto(p)
                if t != p:
                    novas.append(t)
                novas.append(p)
            else:
                novas.append(p)
        return list(dict.fromkeys(novas))

# =========================
# UI SIMPLIFICADA SEM BORDAS
# =========================
class GerenciadorUI:
    def __init__(self, estrutura_temas):
        self.estado = "menu_principal"
        self.estrutura_temas = estrutura_temas
        self.temas_lista = list(estrutura_temas.keys())
        self.tema_selecionado_idx = 0
        self.subtema_selecionado_idx = 0
        self.tema_atual = None
        self.subtema_atual = None
        # ✅ NOVO: Estado para submenu de repetir áudio
        self.submenu_repetir_opcoes = [
            "Repetir áudio gravado",
            "Repetir última resposta"
        ]
        self.submenu_repetir_idx = 0
        self.estado_anterior = None  # Para voltar ao estado anterior

    def mostrar_menu_principal(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        print("=" * 40)
        print("      ASSISTENTE EDUCACIONAL IA")
        print("=" * 40)
        print("W/S - Navegar     ENTER - Selecionar")
        print("4 - Aleatório     3 - Voltar")
        print("R - Repetir áudio")
        print("=" * 40)

    def mostrar_temas(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        print("=" * 40)
        print("         SELECIONE UM TEMA")
        print("=" * 40)
        for i, tema in enumerate(self.temas_lista):
            marcador = ">>>" if i == self.tema_selecionado_idx else "   "
            print(f"{marcador} {tema}")
        print("=" * 40)
        print("W/S - Navegar  ENTER - Selecionar")

    def mostrar_subtemas(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        if not self.tema_atual:
            return
            
        subtemas = self.estrutura_temas.get(self.tema_atual, [])
        print("=" * 40)
        print(f"TEMA: {self.tema_atual}")
        print("=" * 40)
        for i, subtema in enumerate(subtemas):
            marcador = ">>>" if i == self.subtema_selecionado_idx else "   "
            print(f"{marcador} {subtema}")
        print("=" * 40)
        print("W/S - Navegar  ENTER - Selecionar")

    def mostrar_modo_perguntas(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        print("=" * 40)
        print(f"PERGUNTAS: {self.tema_atual}")
        print(f"SUBTEMA: {self.subtema_atual}")
        print("=" * 40)
        print("ENTER - Fazer pergunta com voz")
        print("4 - Pergunta aleatória")
        print("3 - Voltar ao menu anterior")
        print("R - Repetir último áudio")
        print("=" * 40)

    def mostrar_confirmacao(self, pergunta):
        """Mostra tela de confirmação"""
        os.system('cls' if os.name == 'nt' else 'clear')
        print("=" * 40)
        print("      CONFIRMAÇÃO DE PERGUNTA")
        print("=" * 40)
        print("Pergunta capturada:")
        linhas = [pergunta[i:i+38] for i in range(0, len(pergunta), 38)]
        for linha in linhas[:3]:
            print(linha)
        if len(linhas) > 3:
            print("...")
        print("=" * 40)
        print("ENTER - Sim     3 - Não")

    def mostrar_resposta_encontrada(self, pergunta_relacionada, pontuacao, pergunta_original):
        """Mostra tela de resposta encontrada"""
        os.system('cls' if os.name == 'nt' else 'clear')
        print("=" * 40)
        
        # ✅ MOSTRA A QUALIDADE DA CORRESPONDÊNCIA
        if pontuacao >= 5:
            print("  CORRESPONDÊNCIA EXCELENTE")
        elif pontuacao >= 3:
            print("    CORRESPONDÊNCIA BOA")
        elif pontuacao >= 1:
            print(" CORRESPONDÊNCIA MÍNIMA")
        else:
            print(" CORRESPONDÊNCIA ENCONTRADA")
            
        print("=" * 40)
        print("Sua pergunta:")
        linhas_original = [pergunta_original[i:i+38] for i in range(0, len(pergunta_original), 38)]
        for linha in linhas_original[:1]:
            print(linha)
        print("---")
        print("Pergunta relacionada:")
        linhas = [pergunta_relacionada[i:i+38] for i in range(0, len(pergunta_relacionada), 38)]
        for linha in linhas[:2]:
            print(linha)
        if len(linhas) > 2:
            print("...")
        print("=" * 40)
        print("ENTER - Ouvir resposta  3 - Pular")

    def mostrar_sugestoes(self, sugestoes):
        """✅ NOVO: Mostra múltiplas sugestões"""
        os.system('cls' if os.name == 'nt' else 'clear')
        print("=" * 40)
        print("    SUGESTÕES DE PERGUNTAS")
        print("=" * 40)
        
        for i, sugestao in enumerate(sugestoes, 1):
            print(f"SUGESTÃO {i}:")
            print(f"Tema: {sugestao['tema']}")
            print(f"Subtema: {sugestao['subtema']}")
            linhas = [sugestao['pergunta'][i:i+36] for i in range(0, len(sugestao['pergunta']), 36)]
            for linha in linhas[:2]:
                print(linha)
            if i < len(sugestoes):
                print("-" * 40)
        
        print("=" * 40)
        print("Pressione qualquer tecla para continuar")

    def mostrar_aguardando(self, mensagem):
        """Mostra tela de aguardando"""
        os.system('cls' if os.name == 'nt' else 'clear')
        print("=" * 40)
        print("          AGUARDE...")
        print("=" * 40)
        print(mensagem)
        print("O sistema está processando...")
        print("=" * 40)

    # ✅ NOVO: Submenu para repetir áudio
    def mostrar_submenu_repetir(self):
        """Mostra o submenu de repetir áudio"""
        os.system('cls' if os.name == 'nt' else 'clear')
        print("=" * 40)
        print("       SUBMENU REPETIR ÁUDIO")
        print("=" * 40)
        for i, opcao in enumerate(self.submenu_repetir_opcoes):
            marcador = ">>>" if i == self.submenu_repetir_idx else "   "
            print(f"{marcador} {opcao}")
        print("=" * 40)
        print("W/S - Navegar  ENTER - Selecionar  3 - Voltar")

    def entrar_submenu_repetir(self):
        """Entra no submenu de repetir áudio"""
        self.estado_anterior = self.estado
        self.estado = "submenu_repetir"
        self.submenu_repetir_idx = 0
        self.mostrar_submenu_repetir()

    def sair_submenu_repetir(self):
        """Sai do submenu de repetir áudio"""
        self.estado = self.estado_anterior
        self.estado_anterior = None
        
        # Atualiza a tela conforme o estado anterior
        if self.estado == "menu_principal":
            self.mostrar_menu_principal()
        elif self.estado == "escolhendo_tema":
            self.mostrar_temas()
        elif self.estado == "escolhendo_subtema":
            self.mostrar_subtemas()
        elif self.estado == "modo_perguntas":
            self.mostrar_modo_perguntas()

    def navegar_submenu_repetir_cima(self):
        """Navega para cima no submenu"""
        self.submenu_repetir_idx = (self.submenu_repetir_idx - 1) % len(self.submenu_repetir_opcoes)
        self.mostrar_submenu_repetir()

    def navegar_submenu_repetir_baixo(self):
        """Navega para baixo no submenu"""
        self.submenu_repetir_idx = (self.submenu_repetir_idx + 1) % len(self.submenu_repetir_opcoes)
        self.mostrar_submenu_repetir()

    def selecionar_submenu_repetir(self):
        """Retorna a opção selecionada no submenu"""
        return self.submenu_repetir_idx

# =========================
# CONTROLE POR TECLADO SUPER OTIMIZADO
# =========================
class ControladorTeclado:
    def __init__(self):
        self.keyboard = None
        self.ultima_tecla_time = 0
        # Delay para evitar que um único pressionamento de tecla seja registrado várias vezes.
        # 0.3 segundos é um valor que funciona bem para a maioria dos teclados mecânicos e de membrana.
        self.debounce_delay = 0.3
        
        try:
            import keyboard
            self.keyboard = keyboard
            print("🎮 Controle por teclado disponível")
        except ImportError:
            print("⚠️  Biblioteca 'keyboard' não instalada")

    def registrar_callbacks(self, app):
        if not self.keyboard:
            return
            
        try:
            self.keyboard.unhook_all()
            self.keyboard.on_press(lambda e: self._processar_tecla(e, app))
            print("✅ Teclas mapeadas: W, S, ENTER, 4, 3, R")
        except Exception as e:
            print(f"❌ Erro ao configurar teclado: {e}")

    def _processar_tecla(self, evento, app):
        try:
            if evento.event_type == "down":
                current_time = time.time()
                
                # ✅ DEBOUNCE
                if current_time - self.ultima_tecla_time < self.debounce_delay:
                    return
                
                # ✅ BLOQUEIO OTIMIZADO - Usa o método do TTS
                if not app.tts.pode_processar_tecla():
                    print("⏳ Aguarde... Sistema ocupado")
                    return
                
                self.ultima_tecla_time = current_time
                
                # ✅ NOVO: Controle do submenu de repetir
                if app.ui.estado == "submenu_repetir":
                    if evento.name == 'w':
                        app.ui.navegar_submenu_repetir_cima()
                    elif evento.name == 's':
                        app.ui.navegar_submenu_repetir_baixo()
                    elif evento.name == 'enter':
                        app.botao_selecionar_submenu_repetir()
                    elif evento.name == '3':
                        app.ui.sair_submenu_repetir()
                else:
                    # Controles normais
                    if evento.name == 'w':
                        app.botao_cima()
                    elif evento.name == 's':
                        app.botao_baixo()
                    elif evento.name == 'enter':
                        app.botao_selecionar()
                    elif evento.name == '4':
                        app.botao_aleatorio()
                    elif evento.name == '3':
                        app.botao_voltar()
                    elif evento.name == 'r':
                        app.botao_repetir_audio()  # Agora abre submenu
                    
        except Exception as e:
            print(f"❌ Erro ao processar tecla: {e}")

# =========================
# SISTEMA IA PRINCIPAL - MELHORADO
# =========================
class SistemaIA:
    def __init__(self):
        print("🚀 Iniciando Assistente Educacional SUPREMO")
        
        self.tts = GerenciadorTTS()
        self.motor_busca = MotorBusca(Config.PASTA_JSONS)
        self.ui = GerenciadorUI(self.motor_busca.estrutura_temas)
        self.reconhecedor = sr.Recognizer()
        self.controlador = ControladorTeclado()
        
        self.dados_atuais = None
        self.executando = True
        self.ultima_pergunta = None
        self.ultimo_audio = None
        self.ultima_resposta = None  # ✅ NOVO: Guarda a última resposta dada
        
        self.controlador.registrar_callbacks(self)

    def escutar(self):
        """Escuta o microfone"""
        try:
            with sr.Microphone() as fonte:
                self.ui.mostrar_aguardando("Escutando... Fale agora")
                print("🎤 Escutando... FALE AGORA")
                self.reconhecedor.adjust_for_ambient_noise(fonte, duration=0.5)
                audio = self.reconhecedor.listen(fonte, timeout=8, phrase_time_limit=6)
            
            self.ultimo_audio = audio
            
            self.ui.mostrar_aguardando("Processando audio...")
            print("🧠 Processando...")
            texto = self.reconhecedor.recognize_google(audio, language='pt-BR')
            print(f"👤 Você: {texto}")
            
            self.ultima_pergunta = texto
            return texto.lower()
            
        except sr.WaitTimeoutError:
            print("⏰ Tempo esgotado")
            self.tts.falar("Não ouvi nada")
            return ""
        except sr.UnknownValueError:
            print("🤔 Não entendi")
            self.tts.falar("Não consegui entender")
            return ""
        except Exception as e:
            print(f"❌ Erro ao escutar: {e}")
            self.tts.falar("Erro no microfone")
            return ""

    def botao_microfone(self):
        """Sistema de busca completo"""
        if self.ui.estado == "modo_perguntas":
            self.tts.falar("Fale sua pergunta")
            pergunta = self.escutar()
            
            if pergunta:
                self.ui.mostrar_confirmacao(pergunta)
                self.tts.falar(f"Você perguntou: {pergunta}")
                
                print("ENTER para confirmar, 3 para cancelar")
                if self._aguardar_confirmacao():
                    self.ui.mostrar_aguardando("Buscando resposta...")
                    resposta, item_encontrado, pontuacao = self.motor_busca.buscar_resposta_inteligente(
                        pergunta, self.ui.tema_atual, self.ui.subtema_atual
                    )
                    
                    if resposta and item_encontrado:
                        # ✅ NOVO: Guarda a última resposta
                        self.ultima_resposta = resposta
                        self._oferecer_resposta_encontrada(resposta, item_encontrado, pontuacao, pergunta)
                    else:
                        self._lidar_com_falha_busca_melhorado(pergunta)
                else:
                    self.tts.falar("Pergunta cancelada")
                
                self.ui.mostrar_modo_perguntas()
        else:
            self.tts.falar("Selecione um tema primeiro")

    def _lidar_com_falha_busca_melhorado(self, pergunta: str):
            """
            Gerencia a experiência do usuário quando nenhuma resposta é encontrada.

            Em vez de simplesmente informar a falha, este método busca ativamente
            sugestões de perguntas relacionadas (preferencialmente do tema atual)
            para guiar o usuário e manter o engajamento.

            Args:
                pergunta (str): A pergunta original do usuário que não obteve resultado.
            """
            self.tts.falar("Não encontrei uma resposta específica para sua pergunta.")
            time.sleep(0.5)  # Pequena pausa para a fala não ficar corrida.

            # Busca por duas sugestões para oferecer alternativas ao usuário.
            sugestoes = self.motor_busca.obter_sugestoes_perguntas(self.ui.tema_atual, quantidade=2)
            
            if sugestoes:
                self.tts.falar("Aqui estão algumas sugestões de perguntas que você pode fazer:")
                time.sleep(0.5)
                
                # Atualiza a interface de texto para mostrar as sugestões visualmente.
                self.ui.mostrar_sugestoes(sugestoes)
                
                # Vocaliza cada uma das sugestões para o usuário.
                for i, sugestao in enumerate(sugestoes, 1):
                    self.tts.falar(f"Sugestão {i}, do tema {sugestao['tema']}, subtema {sugestao['subtema']}:")
                    self.tts.falar(sugestao['pergunta'])
                    if i < len(sugestoes):
                        time.sleep(0.5) # Pausa entre as sugestões.
                
                self.tts.falar("Essas são sugestões de perguntas relacionadas.")
            else:
                self.tts.falar("Não tenho sugestões no momento.")


    def _oferecer_resposta_encontrada(self, resposta, item_encontrado, pontuacao, pergunta_original):
        """Oferece a resposta encontrada falando a pergunta exata do JSON"""
        pergunta_relacionada = item_encontrado['pergunta']
        self.ui.mostrar_resposta_encontrada(pergunta_relacionada, pontuacao, pergunta_original)
        
        # ✅ FALA A QUALIDADE DA CORRESPONDÊNCIA
        if pontuacao >= 5:
            self.tts.falar("Encontrei uma correspondência excelente")
        elif pontuacao >= 3:
            self.tts.falar("Encontrei uma boa correspondência")  
        elif pontuacao >= 1:
            self.tts.falar("Encontrei uma correspondência mínima")
        else:
            self.tts.falar("Encontrei uma correspondência")
        
        # ✅ FALA A PERGUNTA EXATA DO JSON PARA CONFIRMAR
        self.tts.falar("A pergunta relacionada é:")
        self.tts.falar(pergunta_relacionada)
        
        self.tts.falar("Esta é a resposta que você quer ouvir?")
        print("ENTER para ouvir, 3 para cancelar")
        
        if self._aguardar_confirmacao():
            self.tts.falar(resposta)
        else:
            self.tts.falar("Resposta não reproduzida")

    def _aguardar_confirmacao(self, timeout=8):
        """Aguarda confirmação do usuário"""
        import keyboard
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if keyboard.is_pressed('enter'):
                print("✅ Confirmado")
                time.sleep(0.2)
                return True
            elif keyboard.is_pressed('3'):
                print("❌ Cancelado")
                time.sleep(0.2)
                return False
            time.sleep(0.1)
        
        print("⏰ Tempo esgotado")
        return False

    def botao_repetir_audio(self):
        """✅ ALTERADO: Agora abre o submenu de repetir áudio"""
        if self.ui.estado != "submenu_repetir":
            self.ui.entrar_submenu_repetir()
            self.tts.falar("Submenu repetir áudio. Use W e S para navegar")

    def botao_selecionar_submenu_repetir(self):
        """✅ NOVO: Processa a seleção no submenu de repetir"""
        opcao = self.ui.selecionar_submenu_repetir()
        
        if opcao == 0:  # Repetir áudio gravado
            self._repetir_audio_gravado()
        elif opcao == 1:  # Repetir última resposta
            self._repetir_ultima_resposta()

    def _repetir_audio_gravado(self):
        """Repete o último áudio gravado do usuário"""
        if self.ultimo_audio:
            self.tts.falar("Repetindo áudio gravado")
            try:
                texto = self.reconhecedor.recognize_google(self.ultimo_audio, language='pt-BR')
                self.tts.falar(f"Ouvi: {texto}")
            except Exception as e:
                print(f"❌ Erro ao repetir áudio: {e}")
                self.tts.falar("Erro ao reproduzir áudio")
        else:
            self.tts.falar("Nenhum áudio gravado para repetir")

    def _repetir_ultima_resposta(self):
        """Repete a última resposta dada pela IA"""
        if self.ultima_resposta:
            self.tts.falar("Repetindo última resposta")
            self.tts.falar(self.ultima_resposta)
        else:
            self.tts.falar("Nenhuma resposta anterior para repetir")

    # CONTROLES DE NAVEGAÇÃO VERTICAL
    def botao_cima(self):
        if not self.tts.pode_processar_tecla():
            return
            
        if self.ui.estado == "escolhendo_tema":
            if self.ui.temas_lista:
                self.ui.tema_selecionado_idx = (self.ui.tema_selecionado_idx - 1) % len(self.ui.temas_lista)
                self.ui.mostrar_temas()
                self.tts.falar(self.ui.temas_lista[self.ui.tema_selecionado_idx])
                
        elif self.ui.estado == "escolhendo_subtema":
            subtemas = self.motor_busca.estrutura_temas.get(self.ui.tema_atual, [])
            if subtemas:
                self.ui.subtema_selecionado_idx = (self.ui.subtema_selecionado_idx - 1) % len(subtemas)
                self.ui.mostrar_subtemas()
                self.tts.falar(subtemas[self.ui.subtema_selecionado_idx])

    def botao_baixo(self):
        if not self.tts.pode_processar_tecla():
            return
            
        if self.ui.estado == "escolhendo_tema":
            if self.ui.temas_lista:
                self.ui.tema_selecionado_idx = (self.ui.tema_selecionado_idx + 1) % len(self.ui.temas_lista)
                self.ui.mostrar_temas()
                self.tts.falar(self.ui.temas_lista[self.ui.tema_selecionado_idx])
                
        elif self.ui.estado == "escolhendo_subtema":
            subtemas = self.motor_busca.estrutura_temas.get(self.ui.tema_atual, [])
            if subtemas:
                self.ui.subtema_selecionado_idx = (self.ui.subtema_selecionado_idx + 1) % len(subtemas)
                self.ui.mostrar_subtemas()
                self.tts.falar(subtemas[self.ui.subtema_selecionado_idx])

    def botao_selecionar(self):
        if not self.tts.pode_processar_tecla():
            return
            
        if self.ui.estado == "menu_principal":
            self.ui.estado = "escolhendo_tema"
            self.ui.mostrar_temas()
            self.tts.falar("Escolha um tema")
            
        elif self.ui.estado == "escolhendo_tema":
            self.ui.tema_atual = self.ui.temas_lista[self.ui.tema_selecionado_idx]
            self.ui.estado = "escolhendo_subtema"
            self.ui.mostrar_subtemas()
            self.tts.falar(f"Tema {self.ui.tema_atual}")
            
        elif self.ui.estado == "escolhendo_subtema":
            subtemas = self.motor_busca.estrutura_temas.get(self.ui.tema_atual, [])
            if subtemas:
                self.ui.subtema_atual = subtemas[self.ui.subtema_selecionado_idx]
                self.ui.estado = "modo_perguntas"
                self.iniciar_modo_perguntas()
                
        elif self.ui.estado == "modo_perguntas":
            self.botao_microfone()

    def botao_voltar(self):
        if not self.tts.pode_processar_tecla():
            return
            
        if self.ui.estado == "escolhendo_tema":
            self.ui.estado = "menu_principal"
            self.ui.mostrar_menu_principal()
            self.tts.falar("Menu principal")
        elif self.ui.estado == "escolhendo_subtema":
            self.ui.estado = "escolhendo_tema"
            self.ui.mostrar_temas()
            self.tts.falar("Escolhendo tema")
        elif self.ui.estado == "modo_perguntas":
            self.ui.estado = "escolhendo_subtema"
            self.ui.mostrar_subtemas()
            self.tts.falar("Escolhendo subtema")

    # MODO ALEATÓRIO FUNCIONANDO
    def botao_aleatorio(self):
        if not self.tts.pode_processar_tecla():
            return
            
        if self.ui.estado == "menu_principal":
            self.aleatorio_global()
        elif self.ui.estado == "escolhendo_tema":
            self.aleatorio_tema()
        elif self.ui.estado == "escolhendo_subtema":
            self.aleatorio_subtema_na_lista()
        elif self.ui.estado == "modo_perguntas":
            self.aleatorio_subtema()

    def aleatorio_global(self):
        """Modo aleatório global"""
        self.tts.falar("Pergunta aleatória de toda a base")
        
        item, tema, subtema = self.motor_busca.obter_item_aleatorio_geral()
        
        if item:
            # ✅ NOVO: Guarda a resposta
            self.ultima_resposta = item['resposta']
            self._falar_pergunta_resposta(item, tema, subtema)
        else:
            self.tts.falar("Não encontrei perguntas na base de dados")

    def aleatorio_tema(self):
        """Modo aleatório do tema"""
        if not self.ui.tema_atual: 
            return
        
        self.tts.falar(f"Pergunta aleatória de {self.ui.tema_atual}")
        
        item, subtema = self.motor_busca.obter_item_aleatorio_tema(self.ui.tema_atual)
        
        if item:
            # ✅ NOVO: Guarda a resposta
            self.ultima_resposta = item['resposta']
            self._falar_pergunta_resposta(item, self.ui.tema_atual, subtema)
        else:
            self.tts.falar(f"Não encontrei perguntas em {self.ui.tema_atual}")

    def aleatorio_subtema_na_lista(self):
        if not self.ui.tema_atual: 
            return
            
        subtemas = self.motor_busca.estrutura_temas.get(self.ui.tema_atual, [])
        if subtemas:
            self.ui.subtema_selecionado_idx = random.randint(0, len(subtemas) - 1)
            self.ui.mostrar_subtemas()
            self.tts.falar(f"Subtema: {subtemas[self.ui.subtema_selecionado_idx]}")

    def aleatorio_subtema(self):
        if not self.dados_atuais: 
            return
            
        self.tts.falar("Pergunta aleatória deste subtema")
        item = random.choice(self.dados_atuais)
        # ✅ NOVO: Guarda a resposta
        self.ultima_resposta = item['resposta']
        self._falar_pergunta_resposta(item, self.ui.tema_atual, self.ui.subtema_atual)

    def _falar_pergunta_resposta(self, item, tema, subtema):
        """Fala pergunta e resposta com confirmação"""
        self.tts.falar("Pergunta aleatória")
        self.tts.falar(f"De {tema}, {subtema}")
        self.tts.falar(item['pergunta'])
        
        self.tts.falar("Quer ouvir a resposta?")
        print("ENTER para ouvir, 3 para pular")
        
        if self._aguardar_confirmacao():
            self.tts.falar(item['resposta'])
        else:
            self.tts.falar("Resposta pulada")
        
        self.ui.mostrar_modo_perguntas()

    def iniciar_modo_perguntas(self):
        self.tts.falar(f"Carregando {self.ui.subtema_atual}")
        self.dados_atuais = self.motor_busca.carregar_json(self.ui.tema_atual, self.ui.subtema_atual)
        
        if not self.dados_atuais:
            self.tts.falar("Erro ao carregar dados")
            self.botao_voltar()
            return
            
        self.ui.mostrar_modo_perguntas()
        self.tts.falar(f"Pronto. {len(self.dados_atuais)} perguntas carregadas")

    def mostrar_instrucoes_completas(self):
        """✅ ATUALIZADO: Com apresentação Starlight"""
        if Config.PRIMEIRA_EXECUCAO:
            self.tts.falar("Bem vindo! Sou seu Assistente Educacional, Starlight!")
            time.sleep(0.5)
            self.tts.falar("Use W e S para navegar")
            self.tts.falar("ENTER para selecionar")
            self.tts.falar("Tecla 4 para modo aleatório")
            self.tts.falar("Tecla 3 para voltar")
            self.tts.falar("Tecla R para acessar o menu de repetir áudio")
            time.sleep(0.5)
            self.tts.falar("Atenção importante sobre o sistema de busca:")
            self.tts.falar("Quando você fizer uma pergunta, o sistema buscará a resposta mais relacionada")
            self.tts.falar("A correspondência pode ser excelente, boa, mínima ou apenas relacionada")
            self.tts.falar("Sempre confirmarei a pergunta exata encontrada antes de dar a resposta")
            self.tts.falar("Assim você tem certeza de que é isso que quer ouvir")
            Config.PRIMEIRA_EXECUCAO = False

    def executar(self):
        self.mostrar_instrucoes_completas()
        self.ui.mostrar_menu_principal()
        
        try:
            while self.executando:
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.sair()

    def sair(self):
        print("\n👋 Saindo...")
        self.tts.falar("Até logo! Starlight encerrando")
        self.executando = False
        exit()

# =========================
# EXECUÇÃO
# =========================
if __name__ == "__main__":
    print("🌟 ASSISTENTE EDUCACIONAL STARLIGHT 🌟")
    print("=" * 50)
    
    try:
        ia = SistemaIA()
        ia.executando = True
        ia.executar()
    except KeyboardInterrupt:
        print("\n👋 Sistema encerrado")
    except Exception as e:
        print(f"💥 Erro: {e}")
        input("Pressione Enter para sair...")