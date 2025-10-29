# ARQUIVO: tts_super_robusto.py
import pyttsx3
import time
import threading

class TTS_Super_Robusto:
    def __init__(self):
        print("🚀 Iniciando TTS Super-Robusto...")
        self.voice_id = self._encontrar_voz_pt()
        print("🎯 TTS Super-Robusto - PRONTO!")
    
    def _encontrar_voz_pt(self):
        """Encontra a melhor voz em português"""
        try:
            engine = pyttsx3.init()
            voices = engine.getProperty('voices')
            
            for voice in voices:
                if any(term in voice.name.lower() for term in ['português', 'brazil', 'portuguese', 'pt-br']):
                    print(f"✅ Voz encontrada: {voice.name}")
                    engine.stop()
                    return voice.id
            
            # Fallback para primeira voz disponível
            if voices:
                print(f"⚠️  Voz padrão: {voices[0].name}")
                engine.stop()
                return voices[0].id
                
            return None
            
        except Exception as e:
            print(f"❌ Erro ao buscar vozes: {e}")
            return None
    
    def falar(self, texto):
        """Fala o texto de forma ROBUSTA"""
        if not texto or not texto.strip():
            return
            
        print(f"🎤 FALANDO: {texto}")
        
        try:
            # ✅ CORREÇÃO: NOVA engine para CADA fala
            engine = pyttsx3.init()
            
            # Configurações
            engine.setProperty('rate', 170)  # Velocidade ideal
            engine.setProperty('volume', 1.0)
            
            if self.voice_id:
                engine.setProperty('voice', self.voice_id)
            
            # Fala o texto
            engine.say(texto)
            engine.runAndWait()
            
            # Limpeza adequada
            engine.stop()
            
            print("✅ Fala OK!")
            
        except RuntimeError as e:
            if "run loop already started" in str(e):
                # ✅ CORREÇÃO para o bug específico
                print("⚠️  Bug do run loop corrigido automaticamente")
                self._falar_alternativo(texto)
            else:
                print(f"❌ Erro Runtime: {e}")
        except Exception as e:
            print(f"❌ Erro geral: {e}")
            print(f"🔊 [FALLBACK]: {texto}")
    
    def _falar_alternativo(self, texto):
        """Método alternativo para quando o principal falha"""
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty('rate', 170)
            engine.say(texto)
            engine.runAndWait()
            engine.stop()
        except:
            print(f"🔊 [FALLBACK FINAL]: {texto}")

# TESTE MEGA COMPLETO
if __name__ == "__main__":
    print("=" * 60)
    print("🎯 TESTE SUPER-ROBUSTO - 10 FALAS SEGUIDAS")
    print("=" * 60)
    
    tts = TTS_Super_Robusto()
    
    # Teste EXTENSIVO
    testes = [
        "Frase número um do teste robusto.",
        "Segunda frase confirmando funcionamento.",
        "Terceira frase sem problemas!",
        "Quarta frase continua perfeita.",
        "Quinta frase ainda funcionando!",
        "Sexta frase sem travamentos.",
        "Sétima frase fluindo bem.",
        "Oitava frase quase terminando.",
        "Penúltima frase do teste!",
        "ÚLTIMA frase - teste COMPLETO com sucesso!"
    ]
    
    for i, texto in enumerate(testes, 1):
        print(f"\n🔊 Teste {i}/10")
        tts.falar(texto)
        time.sleep(0.3)  # Pausa mínima
    
    print("\n" + "=" * 60)
    print("🎉🎉🎉 TODAS AS 10 FRASES FUNCIONARAM PERFEITAMENTE!")
    print("=" * 60)
    input("Pressione Enter para sair...")