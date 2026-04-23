"""
QuantEdge AI — LSTM / BiLSTM Derin Öğrenme Modeli
====================================================
Mimari:
  Bidirectional LSTM → Attention → Dense → Output

Neden BiLSTM?
  - Standart LSTM yalnızca geçmişe bakar.
  - BiLSTM hem ileri hem geri yönde öğrenir.
  - Finansal zaman serilerinde desen tespitinde daha güçlü.

Attention Mekanizması:
  Model, sekans içindeki hangi zaman adımlarının daha önemli
  olduğunu öğrenir. Örneğin: earnings açıklaması günü.

MLflow Entegrasyonu:
  Her eğitim run'ı otomatik olarak loglanır.
  Hiperparametreler, metrikler ve model artifact'ları kaydedilir.
"""

import os
from datetime import datetime
from typing import Dict, Optional, Tuple

import numpy as np
import structlog

from app.core.config import settings

logger = structlog.get_logger()


class LSTMModel:
    """
    Bidirectional LSTM + Attention tabanlı fiyat tahmin modeli.

    Kütüphane: TensorFlow/Keras
    Alternatif: PyTorch (pytorch_lstm_model.py olarak eklenebilir)
    """

    def __init__(
        self,
        sequence_length: int = None,
        n_features: int = None,
        hidden_units: int = None,
        dropout_rate: float = None,
        learning_rate: float = 0.001,
    ):
        self.sequence_length = sequence_length or settings.LSTM_SEQUENCE_LENGTH
        self.n_features = n_features or 50  # Dinamik olarak ayarlanır
        self.hidden_units = hidden_units or settings.LSTM_HIDDEN_UNITS
        self.dropout_rate = dropout_rate or settings.LSTM_DROPOUT
        self.learning_rate = learning_rate
        self.model = None
        self.history = None
        self._built = False

    def build(self, n_features: int) -> None:
        """
        Model mimarisini oluşturur.

        Katmanlar:
          1. Input
          2. Bidirectional LSTM (128 units)
          3. Dropout (0.2)
          4. Bidirectional LSTM (64 units)
          5. Dropout (0.2)
          6. Attention Layer (custom)
          7. Dense (32, ReLU)
          8. Output Dense (1, linear) — getiri tahmini
        """
        try:
            import tensorflow as tf
            from tensorflow.keras import layers, Model, Input
            from tensorflow.keras.optimizers import Adam
            from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau
        except ImportError:
            logger.error("TensorFlow bulunamadı. LSTM modeli devre dışı.")
            raise

        self.n_features = n_features
        tf.random.set_seed(42)

        # --- Model Mimarisi ---
        inp = Input(shape=(self.sequence_length, n_features), name="sequence_input")

        # İlk BiLSTM katmanı
        x = layers.Bidirectional(
            layers.LSTM(self.hidden_units, return_sequences=True, name="bilstm_1"),
            name="bidirectional_1"
        )(inp)
        x = layers.Dropout(self.dropout_rate, name="dropout_1")(x)
        x = layers.BatchNormalization(name="bn_1")(x)

        # İkinci BiLSTM katmanı
        x = layers.Bidirectional(
            layers.LSTM(self.hidden_units // 2, return_sequences=True, name="bilstm_2"),
            name="bidirectional_2"
        )(x)
        x = layers.Dropout(self.dropout_rate, name="dropout_2")(x)

        # Attention mekanizması
        x = self._attention_layer(x)

        # Dense katmanlar
        x = layers.Dense(64, activation="relu", name="dense_1")(x)
        x = layers.Dropout(self.dropout_rate / 2)(x)
        x = layers.Dense(32, activation="relu", name="dense_2")(x)

        # Çıktı: normalize getiri tahmini
        output = layers.Dense(1, activation="linear", name="output")(x)

        self.model = Model(inputs=inp, outputs=output, name="QuantEdge_BiLSTM")
        self.model.compile(
            optimizer=Adam(learning_rate=self.learning_rate),
            loss="huber",           # MAE + MSE hibrit — outlier'lara dayanıklı
            metrics=["mae", "mse"],
        )

        self._built = True
        logger.info(
            "LSTM modeli oluşturuldu.",
            params=self.model.count_params(),
            input_shape=(self.sequence_length, n_features),
        )

    def _attention_layer(self, x):
        """
        Basit self-attention mekanizması.
        Hangi zaman adımlarının önemli olduğunu öğrenir.
        """
        try:
            from tensorflow.keras import layers
            # Query-Key-Value attention
            attention_scores = layers.Dense(1, activation="tanh")(x)
            attention_weights = layers.Softmax(axis=1)(attention_scores)
            context = layers.Multiply()([x, attention_weights])
            output = layers.GlobalAveragePooling1D()(context)
            return output
        except Exception:
            # Fallback: GlobalAveragePooling
            from tensorflow.keras import layers
            return layers.GlobalAveragePooling1D()(x)

    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None,
        epochs: int = None,
        batch_size: int = None,
        mlflow_run=None,
    ) -> Dict:
        """
        Modeli eğitir.

        Args:
            X_train   : (samples, seq_len, features)
            y_train   : (samples,) hedef getiri
            X_val     : Validasyon seti (opsiyonel)
            y_val     : Validasyon hedefi
            epochs    : Epoch sayısı
            batch_size: Mini-batch boyutu
            mlflow_run: Aktif MLflow run (logging için)

        Returns:
            Eğitim metrikleri
        """
        if not self._built:
            self.build(X_train.shape[2])

        epochs = epochs or settings.LSTM_EPOCHS
        batch_size = batch_size or settings.LSTM_BATCH_SIZE

        try:
            from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau, ModelCheckpoint
        except ImportError:
            logger.error("TensorFlow callback'leri yüklenemedi.")
            raise

        callbacks = [
            EarlyStopping(
                monitor="val_loss" if X_val is not None else "loss",
                patience=15,
                restore_best_weights=True,
                verbose=0,
            ),
            ReduceLROnPlateau(
                monitor="val_loss" if X_val is not None else "loss",
                factor=0.5,
                patience=7,
                min_lr=1e-6,
                verbose=0,
            ),
        ]

        validation_data = (X_val, y_val) if X_val is not None and y_val is not None else None

        logger.info("LSTM eğitimi başlıyor.", epochs=epochs, batch_size=batch_size, samples=len(X_train))

        self.history = self.model.fit(
            X_train, y_train,
            epochs=epochs,
            batch_size=batch_size,
            validation_data=validation_data,
            callbacks=callbacks,
            verbose=0,
            shuffle=False,   # Zaman serisi — karıştırma!
        )

        # Eğitim metrikleri
        metrics = {
            "final_train_loss": float(self.history.history["loss"][-1]),
            "final_train_mae": float(self.history.history["mae"][-1]),
            "epochs_trained": len(self.history.history["loss"]),
        }

        if validation_data:
            metrics["final_val_loss"] = float(self.history.history["val_loss"][-1])
            metrics["final_val_mae"] = float(self.history.history["val_mae"][-1])

        # MLflow loglama
        if mlflow_run:
            try:
                import mlflow
                mlflow.log_metrics(metrics)
                mlflow.log_params({
                    "lstm_hidden_units": self.hidden_units,
                    "lstm_dropout": self.dropout_rate,
                    "lstm_sequence_length": self.sequence_length,
                    "lstm_epochs_trained": metrics["epochs_trained"],
                })
            except Exception as e:
                logger.warning("MLflow loglama hatası.", error=str(e))

        logger.info("LSTM eğitimi tamamlandı.", **metrics)
        return metrics

    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Getiri tahmini yapar.

        Args:
            X: (samples, seq_len, features)

        Returns:
            Tahmin edilen getiriler (samples,)
        """
        if not self._built or self.model is None:
            raise RuntimeError("Model henüz eğitilmedi. Önce train() çağırın.")

        predictions = self.model.predict(X, verbose=0)
        return predictions.flatten()

    def predict_with_uncertainty(
        self,
        X: np.ndarray,
        n_samples: int = 50,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Monte Carlo Dropout ile belirsizlik tahmini.
        Dropout train modunda tutularak stochastic tahmin yapılır.
        Bu, güven aralığı (confidence interval) sağlar.

        Args:
            X        : Input sekanslar
            n_samples: MC örneklem sayısı (50 yeterli)

        Returns:
            (mean, lower_bound, upper_bound)
        """
        if self.model is None:
            raise RuntimeError("Model henüz eğitilmedi.")

        try:
            import tensorflow as tf
        except ImportError:
            preds = self.predict(X)
            return preds, preds * 0.95, preds * 1.05

        # Dropout'u aktif tut (train=True)
        predictions = []
        for _ in range(n_samples):
            pred = self.model(X, training=True).numpy().flatten()
            predictions.append(pred)

        predictions = np.array(predictions)   # (n_samples, batch)
        mean = predictions.mean(axis=0)
        std = predictions.std(axis=0)

        # %90 güven aralığı (1.645 * std)
        lower = mean - 1.645 * std
        upper = mean + 1.645 * std

        return mean, lower, upper

    def save(self, ticker: str, timeframe: str) -> str:
        """Modeli diske kaydeder."""
        if self.model is None:
            raise RuntimeError("Kaydedilecek model yok.")

        path = os.path.join(
            settings.MODEL_ARTIFACTS_PATH,
            "lstm",
            ticker,
            f"{timeframe}.keras",
        )
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.model.save(path)
        logger.info("LSTM modeli kaydedildi.", path=path)
        return path

    def load(self, ticker: str, timeframe: str) -> bool:
        """Kaydedilmiş modeli yükler."""
        try:
            import tensorflow as tf
            path = os.path.join(
                settings.MODEL_ARTIFACTS_PATH,
                "lstm",
                ticker,
                f"{timeframe}.keras",
            )
            if not os.path.exists(path):
                return False
            self.model = tf.keras.models.load_model(path)
            self._built = True
            logger.info("LSTM modeli yüklendi.", ticker=ticker, timeframe=timeframe)
            return True
        except Exception as e:
            logger.warning("LSTM model yükleme hatası.", error=str(e))
            return False

    @property
    def summary(self) -> str:
        """Model özeti."""
        if self.model:
            lines = []
            self.model.summary(print_fn=lines.append)
            return "\n".join(lines)
        return "Model henüz oluşturulmadı."
